from io import BytesIO
import os
from django.conf import settings
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.auth import login_required_custom
from apps.core.models import Inventario, MovimientoInventario, Producto, Usuario

from .forms import MovementForm, ProductForm
from .services import (
    build_product_form_initial,
    build_rows,
    categories_and_providers,
    inventory_queryset,
    movement_history,
    report_kpis,
    report_summary,
    sort_rows,
)
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import json


# =========================================================================
# ⚙️ FUNCIONES AUXILIARES PRIVADAS
# =========================================================================

def _build_product_form(product=None):
    """Construye el formulario de producto con las categorías y proveedores disponibles."""
    data = categories_and_providers()
    return ProductForm(initial=build_product_form_initial(product), categories=data["categories"], providers=data["providers"])


def _current_user(request):
    """Devuelve el usuario activo de la sesión o None si no hay sesión iniciada."""
    user_id = request.session.get("id_usuario")
    if not user_id:
        return None
    return Usuario.objects.filter(id_usuario=user_id).first()


def _selected_product_from_request(request):
    """Extrae el producto seleccionado de los parámetros GET de la solicitud."""
    selected_id = (request.GET.get("product") or request.GET.get("producto_id") or "").strip()
    if not selected_id:
        return None
    return Producto.objects.select_related("id_categoria", "id_proveedor").filter(id_producto=selected_id).first()


def _parse_optional_date(request, key):
    """Lee y convierte a objeto date un parámetro GET opcional."""
    raw = (request.GET.get(key) or "").strip()
    if not raw:
        return None
    return parse_date(raw)


def _excel_safe_datetime(value):
    """Convierte un datetime con zona horaria a uno sin zona (naive) para reportes."""
    if not value:
        return ""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
        return value.replace(tzinfo=None)
    return value


# =========================================================================
# 🏠 VISTA PRINCIPAL: LISTADO Y NAVEGACIÓN DEL INVENTARIO
# =========================================================================

@login_required_custom
def index(request):
    """
    Vista principal del registro de inventario (GET).
    Muestra la tabla general, KPIs superiores y prepara los formularios con soporte para filtros combinados.
    """
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete_product":
            return _delete_product(request)
        if action == "save_movement":
            return _save_movement(request)

    # Leer parámetros de búsqueda, filtros avanzados y ordenamiento desde la URL
    query_text = (request.GET.get("q") or "").strip()
    category_id = (request.GET.get("category") or "").strip()
    stock_range = (request.GET.get("stock_range") or "").strip()
    provider_id = (request.GET.get("provider") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    sort_key = (request.GET.get("sort") or "codigo").strip()
    
    sort_key = (request.GET.get("sort") or "codigo").strip()
    per_page_raw = (request.GET.get("per_page") or "25").strip()
    try:
        per_page = max(5, min(int(per_page_raw), 100))
    except ValueError:
        per_page = 25

    # Obtener y ordenar las filas del inventario usando la función con los 5 filtros aplicados
    queryset = inventory_queryset(
        query_text=query_text, 
        category_id=category_id,
        stock_range=stock_range,
        provider_id=provider_id,
        status_filter=status_filter
    )
    rows = sort_rows(build_rows(queryset), sort_key)
    total_registros = len(rows)
    stock_bajo = sum(1 for row in rows if row["estado"] == "Bajo")
    stock_cero = sum(1 for row in rows if row["estado"] == "Agotado")
    hoy = timezone.localdate()
    movimientos_hoy = MovimientoInventario.objects.filter(fecha_movimiento__date=hoy).count()

    # Paginación server-side
    page = request.GET.get('page', 1)
    paginator = Paginator(rows, per_page)
    try:
        rows_page = paginator.page(page)
    except PageNotAnInteger:
        rows_page = paginator.page(1)
    except EmptyPage:
        rows_page = paginator.page(paginator.num_pages)

    # Determinar el producto seleccionado (URL o primero de la lista)
    selected_product = _selected_product_from_request(request)
    if not selected_product and rows:
        selected_product = rows[0]["product"]

    # Buscar la fila que corresponde al producto seleccionado para resaltarla
    selected_row = None
    if selected_product:
        for row in rows:
            if row["codigo"] == selected_product.id_producto:
                selected_row = row
                break

    product_form = _build_product_form(selected_product)
    movement_form = MovementForm()

    catalogos = categories_and_providers()
    categories = catalogos["categories"]
    providers = catalogos["providers"]
    product_options = list(inventory_queryset().values("id_producto", "nombre"))

    context = {
        "categories": categories,
        "providers": providers,
        "rows": rows_page.object_list,
        "page_obj": rows_page,
        "paginator": paginator,
        "per_page": per_page,
        "selected_row": selected_row,
        "product_form": product_form,
        "movement_form": movement_form,
        "query_text": query_text,
        "category_id": category_id,
        "stock_range": stock_range,
        "provider_id": provider_id,
        "status_filter": status_filter,
        "sort_key": sort_key,
        "total_registros": total_registros,
        "stock_bajo": stock_bajo,
        "stock_cero": stock_cero,
        "movimientos_hoy": movimientos_hoy,
        "selected_product_id": selected_product.id_producto if selected_product else "",
        "selected_product_name": selected_product.nombre if selected_product else "",
        "product_options": product_options,
    }
    return render(request, "registro/index.html", context)


# =========================================================================
# 💾 ENDPOINTS API (AJAX / FETCH)
# =========================================================================

@login_required_custom
def guardar_edicion_producto_api(request):
    """Endpoint AJAX para procesar de forma segura la EDICIÓN de productos."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Método no permitido"}, status=405)

    data_catalogos = categories_and_providers()
    form = ProductForm(request.POST, categories=data_catalogos["categories"], providers=data_catalogos["providers"])
    
    if not form.is_valid():
        return JsonResponse({"success": False, "errors": form.errors}, status=400)

    clean_data = form.cleaned_data
    try:
        with transaction.atomic():
            product = Producto.objects.select_for_update().get(pk=clean_data["product_id"])
            product.nombre = clean_data["nombre"]
            product.descripcion = clean_data["descripcion"]
            product.id_categoria_id = clean_data["categoria"]
            product.id_proveedor_id = clean_data["proveedor"] or None
            product.precio_compra = clean_data["precio_compra"]
            product.precio_venta = clean_data["precio_venta"]
            product.unidad_medida = clean_data["unidad_medida"]
            product.save()

            inventario, _ = Inventario.objects.get_or_create(id_producto=product)
            inventario.stock_minimo = clean_data["stock_minimo"]
            inventario.fecha_actualizacion = timezone.now()
            inventario.save()

        return JsonResponse({"success": True, "message": "Producto modificado con éxito."})
    except Producto.DoesNotExist:
        return JsonResponse({"success": False, "error": "El producto seleccionado no existe en el sistema."}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Error crítico de base de datos: {str(e)}"}, status=500)


@require_GET
def autocomplete_products(request):
    """API simple que devuelve sugerencias de productos para el datalist."""
    q = (request.GET.get('q') or '').strip()
    if not q:
        return JsonResponse([], safe=False)

    qs = inventory_queryset(query_text=q)
    suggestions = list(qs.values('id_producto', 'nombre')[:12])
    return JsonResponse(suggestions, safe=False)


@require_POST
@login_required_custom
@require_POST
def quick_update_product(request):
    """
    API asíncrona optimizada para modificar la información completa 
    de un artículo directamente desde la interfaz de inventario.
    """
    try:
        data = json.loads(request.body)
        id_producto = data.get('id_producto')
        
        if not id_producto:
            return JsonResponse({'ok': False, 'error': 'El código identificador del producto es requerido.'})
            
        producto = Producto.objects.filter(id_producto=id_producto).first()
        if not producto:
            return JsonResponse({'ok': False, 'error': 'El artículo seleccionado no existe en el sistema.'})

        # Capturar el set extendido de datos
        nombre = data.get('nombre')
        id_categoria = data.get('id_categoria')
        id_proveedor = data.get('id_proveedor')
        unidad_medida = data.get('unidad_medida')
        estado = data.get('estado')
        precio_compra = data.get('precio_compra')
        precio_venta = data.get('precio_venta')
        stock_actual = data.get('stock_actual')
        stock_minimo = data.get('stock_minimo')

        with transaction.atomic():
            if nombre:
                producto.nombre = nombre.strip()
            if unidad_medida:
                producto.unidad_medida = unidad_medida
            if estado:
                producto.estado = estado
                
            # Asignación numérica con validación de tipo básica
            if precio_compra is not None:
                producto.precio_compra = float(precio_compra)
            if precio_venta is not None:
                producto.precio_venta = float(precio_venta)
            if stock_actual is not None:
                producto.stock_actual = int(stock_actual)
            if stock_minimo is not None:
                producto.stock_minimo = int(stock_minimo)

            # Asignación segura de llaves extranjeras (Categoría y Proveedor)
            if id_categoria:
                producto.id_categoria_id = int(id_categoria)
            if id_proveedor:
                producto.id_proveedor_id = int(id_proveedor)

            producto.save()

        return JsonResponse({'ok': True})

    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Formato JSON corrupto o inválido.'})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)})
    
# =========================================================================
# 🚫 ACCIONES TRADICIONALES POST
# =========================================================================

def _delete_product(request):
    """Elimina un producto y todos sus datos relacionados."""
    product_id = (request.POST.get("product_id") or "").strip()
    if not product_id:
        messages.error(request, "Selecciona un producto para eliminar.")
        return redirect(request.path)

    try:
        with transaction.atomic():
            product = Producto.objects.select_for_update().get(pk=product_id)
            Inventario.objects.filter(id_producto=product).delete()
            MovimientoInventario.objects.filter(id_producto=product).delete()
            product.delete()
        messages.success(request, "Producto eliminado correctamente del almacén.")
    except Producto.DoesNotExist:
        messages.error(request, "El producto ya no existe.")
    except IntegrityError:
        messages.error(request, "No se puede eliminar: existen facturas o registros amarrados a este artículo.")
    return redirect(request.path)


def _save_movement(request):
    """Registra ajustes manuales de stock, auditando entradas o salidas."""
    form = MovementForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Revisa los campos del movimiento antes de guardar.")
        return _render_with_form(request, movement_form=form)

    data = form.cleaned_data
    product = _resolve_product_from_label(data["producto"])
    if not product:
        messages.error(request, "No se pudo identificar el producto del movimiento.")
        return _render_with_form(request, movement_form=form)

    delta = data["cantidad"]
    if data["tipo_movimiento"] in {"salida", "ajuste_salida"}:
        delta = -delta

    try:
        with transaction.atomic():
            inventario, _ = Inventario.objects.select_for_update().get_or_create(id_producto=product)
            actual = inventario.stock_actual or 0
            nuevo = actual + delta
            if nuevo < 0:
                raise ValueError("Operación denegada: El stock resultante no puede quedar en negativo.")
            inventario.stock_actual = nuevo
            if inventario.stock_minimo is None:
                inventario.stock_minimo = 0
            inventario.fecha_actualizacion = timezone.now()
            inventario.save()

            MovimientoInventario.objects.create(
                id_producto=product,
                id_usuario=_current_user(request),
                tipo_movimiento=data["tipo_movimiento"],
                cantidad=data["cantidad"],
                referencia=f"{data['tipo_movimiento']} - {product.nombre}",
                fecha_movimiento=timezone.now(),
                observaciones=data["observacion"],
            )
        messages.success(request, "Movimiento de stock registrado de manera exitosa.")
        return redirect(f"{request.path}?product={product.id_producto}")
    except ValueError as exc:
        messages.error(request, str(exc))
    except IntegrityError as exc:
        messages.error(request, f"No se pudo registrar el movimiento: {exc}")
    return _render_with_form(request, movement_form=form)


def _resolve_product_from_label(label):
    """Resuelve un producto a partir de la etiqueta proveniente de la interfaz."""
    raw = (label or "").strip()
    if not raw:
        return None
    token = raw.split("|")[0].strip()
    try:
        product_id = int(token)
    except ValueError:
        return Producto.objects.filter(nombre__iexact=raw).first()
    return Producto.objects.filter(id_producto=product_id).first()


def _render_with_form(request, product_form=None, movement_form=None):
    """Re-renderizador auxiliar utilizado en fallos de envíos tradicionales POST."""
    query_text = (request.GET.get("q") or "").strip()
    category_id = (request.GET.get("category") or "").strip()
    sort_key = (request.GET.get("sort") or "codigo").strip()
    queryset = inventory_queryset(query_text=query_text, category_id=category_id)
    rows = sort_rows(build_rows(queryset), sort_key)
    selected_product = _selected_product_from_request(request)
    if not selected_product and rows:
        selected_product = rows[0]["product"]
    selected_row = None
    if selected_product:
        for row in rows:
            if row["codigo"] == selected_product.id_producto:
                selected_row = row
                break

    if product_form is None:
        product_form = _build_product_form(selected_product)
    if movement_form is None:
        movement_form = MovementForm()

    context = {
        "categories": categories_and_providers()["categories"],
        "rows": rows,
        "selected_row": selected_row,
        "product_form": product_form,
        "movement_form": movement_form,
        "query_text": query_text,
        "category_id": category_id,
        "sort_key": sort_key,
        "selected_product_id": selected_product.id_producto if selected_product else "",
        "selected_product_name": selected_product.nombre if selected_product else "",
        "product_options": list(inventory_queryset().values("id_producto", "nombre")),
    }
    return render(request, "registro/index.html", context)

@login_required_custom
def exportar_inventario_pdf(request):
    """
    Genera un reporte PDF específico con la lista de productos y sus existencias actuales.
    - Aplica filtros avanzados: búsqueda por texto, categoría, rango de stock, proveedor y estado.
    - Se abre 'inline' en una pestaña nueva del navegador.
    - Guarda automáticamente una copia física de respaldo en el servidor.
    """
    # 1. Capturar los filtros activos de la tabla de inventario enviados por la barra de herramientas
    query_text = (request.GET.get("q") or "").strip()[:100]
    category_id = (request.GET.get("category") or "").strip()
    
    # Nuevos parámetros avanzados capturados
    stock_range = (request.GET.get("stock_range") or "").strip()
    provider_id = (request.GET.get("provider") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    
    sort_key = (request.GET.get("sort") or "codigo").strip()

    # 2. Obtener y ordenar los datos usando los servicios avanzados existentes (Con soporte para los 5 filtros)
    queryset = inventory_queryset(
        query_text=query_text, 
        category_id=category_id,
        stock_range=stock_range,
        provider_id=provider_id,
        status_filter=status_filter
    )
    rows = sort_rows(build_rows(queryset), sort_key)

    # 3. Preparar el documento PDF en memoria
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=18, leftMargin=18, topMargin=18, bottomMargin=18)
    styles = getSampleStyleSheet()
    elements = []

    logo_path = os.path.join(settings.BASE_DIR, "static", "assets", "Ferreteria.png")
    now_local = timezone.localtime(timezone.now())
    report_number = f"INV-{now_local.strftime('%Y%m%d-%H%M%S')}"

    if os.path.exists(logo_path):
        logo_cell = Image(logo_path, width=150, height=78)
    else:
        logo_cell = Paragraph("<b>FERRETERIA<br/>MI CASA</b>", styles["Heading1"])

    report_box = Table([
        [Paragraph(f"<b>REPORTE N°: {report_number}</b>", styles["BodyText"])],
        [Paragraph(f"<b>FECHA: {now_local.strftime('%d/%m/%Y')}</b>", styles["BodyText"])],
    ], colWidths=[170])
    report_box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 1, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    elements.append(Table([
        [logo_cell, report_box],
    ], colWidths=[doc.width - 190, 190], style=TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ])))
    elements.append(Spacer(1, 10))

    # Bloque de información general y metadatos de los filtros aplicados
    info_table = Table([
        [
            Paragraph("<b>DATOS DE LA EMPRESA</b>", styles["Heading3"]),
            Paragraph("<b>FILTROS DEL INVENTARIO</b>", styles["Heading3"])
        ],
        [
            Paragraph("Dirección: Granada Diriomo, de la entrada principal de Diriomo una cuadra al Norte a mano izquierda", styles["BodyText"]),
            Paragraph(f"Búsqueda activa: {query_text or 'Ninguna (Todos)'}<br/>Categoría ID: {category_id or 'Todas'}<br/>Rango Stock: {stock_range or 'Todos'}", styles["BodyText"]),
        ],
        [
            Paragraph("Teléfono: +505 8765-4321", styles["BodyText"]),
            Paragraph(f"Proveedor ID: {provider_id or 'Todos'}<br/>Estado: {status_filter or 'Todos'}<br/>Ordenado por: {sort_key}", styles["BodyText"]),
        ],
        [
            Paragraph("Email: admin.ferreteria@gmail.com", styles["BodyText"]),
            Paragraph(f"<b>Total registros exportados: {len(rows)} artículos</b>", styles["BodyText"]),
        ],
    ], colWidths=[doc.width / 2, doc.width / 2])
    info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("<b>Existencias y Precios Actuales en Almacén</b>", styles["Heading2"]))
    elements.append(Spacer(1, 6))

    # 4. Estructurar la Tabla con las columnas del Inventario (Mapeando Proveedor en lugar del Stock Mínimo)
    headers = ["Código", "Descripción / Producto", "Categoría", "U. Medida", "P. Compra", "P. Venta", "Stock Act.", "Proveedor", "Estado"]
    table_data = [headers]

    for r in rows:
        table_data.append([
            Paragraph(str(r["codigo"]), styles["BodyText"]),
            Paragraph(str(r["nombre"]), styles["BodyText"]),
            Paragraph(str(r["categoria"]), styles["BodyText"]),
            Paragraph(str(r["unidad_medida"]), styles["BodyText"]),
            Paragraph(f"C$ {r['precio_compra']:.2f}", styles["BodyText"]),
            Paragraph(f"C$ {r['precio_venta']:.2f}", styles["BodyText"]),
            Paragraph(str(r["stock_actual"]), styles["BodyText"]),
            Paragraph(str(r["proveedor"] or "Sin Proveedor"), styles["BodyText"]),
            Paragraph(str(r["estado"]), styles["BodyText"]),
        ])

    # Anchos de columna balanceados (Total: 806px de margen a margen en hoja A4 horizontal)
    inv_table = Table(
        table_data,
        repeatRows=1,
        colWidths=[55, 185, 105, 55, 65, 65, 55, 165, 56]
    )
    inv_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B4EA2")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("LEADING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(inv_table)
    
    # Construir PDF en memoria
    doc.build(elements)
    pdf_content = buffer.getvalue()
    buffer.close()

    # 5. Guardado físico automático de la copia de respaldo en la carpeta local
    try:
        ruta_destino = settings.SUBCARPETAS_FERRETERIA.get("Inventarios") or settings.SUBCARPETAS_FERRETERIA.get("Inventario")
        if ruta_destino:
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            nombre_archivo = f"Reporte_Inventario_Stock_{timestamp}.pdf"
            ruta_completa = os.path.join(ruta_destino, nombre_archivo)
            
            with open(ruta_completa, "wb") as f_local:
                f_local.write(pdf_content)
            print(f"[RESPALDO] Inventario guardado en: {ruta_completa}")
    except Exception as e:
        print(f"[ALERTA RESPALDO] No se guardó copia local del inventario: {e}")

    # 6. Responder al navegador para abrir inline en pestaña nueva
    response = HttpResponse(pdf_content, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="inventario_general.pdf"'
    return response

# =========================================================================
# 📊 GENERACIÓN DE REPORTES
# =========================================================================

@login_required_custom
def export_excel(request):
    """Genera un reporte PDF de los movimientos de almacén."""
    query_text = (request.GET.get("q") or "").strip()[:100]
    category_id = (request.GET.get("category") or "").strip()
    product_id = (request.GET.get("product") or "").strip()
    movement_type = (request.GET.get("movement_type") or "").strip()
    start_date = _parse_optional_date(request, "from")
    end_date = _parse_optional_date(request, "to")
    
    movements = report_kpis(
        product_id=product_id,
        movement_type=movement_type,
        start_date=start_date,
        end_date=end_date,
        query_text=query_text,
        category_id=category_id,
    )["movements"]

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=18, leftMargin=18, topMargin=18, bottomMargin=18)
    styles = getSampleStyleSheet()
    elements = []

    logo_path = os.path.join(settings.BASE_DIR, "static", "assets", "Ferreteria.png")
    now_local = timezone.localtime(timezone.now())
    report_number = f"REP-{now_local.strftime('%Y%m%d-%H%M%S')}"

    if os.path.exists(logo_path):
        logo_cell = Image(logo_path, width=150, height=78)
    else:
        logo_cell = Paragraph("<b>FERRETERIA<br/>MI CASA</b>", styles["Heading1"])

    report_box = Table([
        [Paragraph(f"<b>REPORTE N°: {report_number}</b>", styles["BodyText"])],
        [Paragraph(f"<b>FECHA: {now_local.strftime('%d/%m/%Y')}</b>", styles["BodyText"])],
    ], colWidths=[170])
    report_box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 1, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    elements.append(Table([
        [logo_cell, report_box],
    ], colWidths=[doc.width - 190, 190], style=TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ])))
    elements.append(Spacer(1, 10))

    elements.append(Table([
        [Paragraph("<b>DATOS DE LA EMPRESA</b>", styles["Heading2"]), Paragraph("<b>DATOS DEL REPORTE</b>", styles["Heading2"])]
    ], colWidths=[doc.width / 2, doc.width / 2], style=TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])))

    info_table = Table([
        [
            Paragraph("Dirección: Granada Diriomo, de la entrada principal de Diriomo una cuadra al Norte a mano izquierda", styles["BodyText"]),
            Paragraph(f"Filtros aplicados:<br/>Producto: {product_id or 'Todos'}<br/>Tipo: {movement_type or 'Todos'}<br/>Desde: {request.GET.get('from', '') or 'N/A'}<br/>Hasta: {request.GET.get('to', '') or 'N/A'}<br/>Búsqueda: {query_text or 'N/A'}<br/>Categoría: {category_id or 'Todas'}", styles["BodyText"]),
        ],
        [
            Paragraph("Teléfono: +505 8765-4321", styles["BodyText"]),
            Paragraph("Reporte generado desde el módulo de inventario", styles["BodyText"]),
        ],
        [
            Paragraph("RUC/NIT: J-12345678-9", styles["BodyText"]),
            Paragraph(f"Usuario: {request.session.get('id_usuario') or 'Sistema'}", styles["BodyText"]),
        ],
        [
            Paragraph("Email: admin.ferreteria@gmail.com", styles["BodyText"]),
            Paragraph("", styles["BodyText"]),
        ],
    ], colWidths=[doc.width / 2, doc.width / 2])
    info_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("<b>Movimientos de inventario</b>", styles["Heading2"]))
    elements.append(Spacer(1, 6))

    mov_header = ["Fecha", "Producto", "Tipo", "Cantidad", "Usuario", "Observación"]
    mov_data = [mov_header]
    for movement in movements[:200]:
        mov_data.append([
            Paragraph(str(_excel_safe_datetime(movement.fecha_movimiento)), styles["BodyText"]),
            Paragraph(str(movement.id_producto.nombre) if movement.id_producto else "", styles["BodyText"]),
            Paragraph(str(movement.tipo_movimiento), styles["BodyText"]),
            Paragraph(str(movement.cantidad), styles["BodyText"]),
            Paragraph(str(movement.id_usuario.nombre) if movement.id_usuario else "Sistema", styles["BodyText"]),
            Paragraph(str(movement.observaciones or ""), styles["BodyText"]),
        ])
    mov_table = Table(
        mov_data,
        repeatRows=1,
        colWidths=[95, 190, 70, 55, 115, doc.width - 525],
    )
    mov_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B4EA2")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.8, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("LEADING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(mov_table)

    doc.build(elements)
    pdf_content = buffer.getvalue()
    buffer.close()

    try:
        ruta_destino = settings.SUBCARPETAS_FERRETERIA.get("Inventario") or settings.SUBCARPETAS_FERRETERIA.get("Reportes")
        if ruta_destino:
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            nombre_archivo_fisico = f"Reporte_Movimientos_{timestamp}.pdf"
            ruta_completa = os.path.join(ruta_destino, nombre_archivo_fisico)
            with open(ruta_completa, "wb") as f_local:
                f_local.write(pdf_content)
    except Exception as e:
        print(f"[ALERTA RESPALDO] Copia local no escrita: {e}")

    response = HttpResponse(pdf_content, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="movimientos_ferreteria.pdf"'
    return response


@login_required_custom
def reportes(request):
    """Vista de estadísticas, KPIs macro de existencias y flujos de almacén."""
    query_text = (request.GET.get("q") or "").strip()[:100]
    category_id = (request.GET.get("category") or "").strip()
    product_id = (request.GET.get("product") or "").strip()
    movement_type = (request.GET.get("movement_type") or "").strip()
    start_date = _parse_optional_date(request, "from")
    end_date = _parse_optional_date(request, "to")
    per_page_raw = (request.GET.get("per_page") or "15").strip()
    try:
        per_page = max(5, min(int(per_page_raw), 100))
    except ValueError:
        per_page = 15

    inv_qs = inventory_queryset(query_text=query_text, category_id=category_id)
    if product_id:
        inv_qs = inv_qs.filter(id_producto=product_id)
    rows = sort_rows(build_rows(inv_qs), "codigo")
    summary = report_summary(inventory_queryset(query_text=query_text, category_id=category_id))
    kpis = report_kpis(product_id=product_id, movement_type=movement_type, start_date=start_date, end_date=end_date, query_text=query_text, category_id=category_id)
    movements_queryset = kpis["movements"]
    
    paginator = Paginator(movements_queryset, per_page)
    page = request.GET.get("page", 1)
    try:
        movements_page = paginator.page(page)
    except PageNotAnInteger:
        movements_page = paginator.page(1)
    except EmptyPage:
        movements_page = paginator.page(paginator.num_pages)

    selected_product = _selected_product_from_request(request)
    if not selected_product and product_id:
        selected_product = Producto.objects.filter(id_producto=product_id).first()

    context = {
        "categories": categories_and_providers()["categories"],
        "rows": rows,
        "summary": summary,
        "movements": movements_page.object_list,
        "page_obj": movements_page,
        "paginator": paginator,
        "per_page": per_page,
        "total_entradas": kpis["total_entradas"],
        "total_salidas": kpis["total_salidas"],
        "conteo_movimientos": kpis["conteo_movimientos"],
        "query_text": query_text,
        "category_id": category_id,
        "product_id": product_id,
        "movement_type": movement_type,
        "start_date": request.GET.get("from", ""),
        "end_date": request.GET.get("to", ""),
        "selected_product_name": selected_product.nombre if selected_product else "",
        "product_options": list(inventory_queryset().values("id_producto", "nombre")),
    }
    return render(request, "registro/reportes.html", context)