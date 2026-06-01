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
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

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
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_POST
from django.middleware.csrf import get_token
import json


# Funciones auxiliares privadas

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
    """
    Extrae el producto seleccionado de los parámetros GET de la solicitud
    (parámetros 'product' o 'producto_id').
    Retorna el objeto Producto o None si no se encuentra.
    """
    selected_id = (request.GET.get("product") or request.GET.get("producto_id") or "").strip()
    if not selected_id:
        return None
    return Producto.objects.select_related("id_categoria", "id_proveedor").filter(id_producto=selected_id).first()


def _parse_optional_date(request, key):
    """
    Lee y convierte a objeto date un parámetro GET opcional.
    Devuelve None si el parámetro no existe o no es una fecha válida.
    """
    raw = (request.GET.get(key) or "").strip()
    if not raw:
        return None
    return parse_date(raw)


def _excel_safe_datetime(value):
    """
    Convierte un datetime con zona horaria a uno sin zona (naive) para que
    openpyxl pueda escribirlo correctamente en una celda de Excel.
    """
    if not value:
        return ""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
        return value.replace(tzinfo=None)
    return value


# Vista principal: listado y gestión de inventario

@login_required_custom
def index(request):
    """
    Vista principal del registro de inventario.
    - GET: muestra la tabla de productos con el formulario de edición y movimientos.
    - POST: delega en _save_product, _delete_product o _save_movement según la acción enviada.
    """
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_product":
            return _save_product(request)
        if action == "delete_product":
            return _delete_product(request)
        if action == "save_movement":
            return _save_movement(request)

    # Leer parámetros de búsqueda, filtro y ordenamiento desde la URL
    query_text = (request.GET.get("q") or "").strip()
    category_id = (request.GET.get("category") or "").strip()
    sort_key = (request.GET.get("sort") or "codigo").strip()
    per_page_raw = (request.GET.get("per_page") or "25").strip()
    try:
        per_page = max(5, min(int(per_page_raw), 100))
    except ValueError:
        per_page = 25

    # Obtener y ordenar las filas del inventario según los filtros activos
    queryset = inventory_queryset(query_text=query_text, category_id=category_id)
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

    categories = categories_and_providers()["categories"]
    # Opciones para el datalist del campo de producto en el formulario de movimientos
    product_options = list(inventory_queryset().values("id_producto", "nombre"))

    context = {
        "categories": categories,
        "rows": rows_page.object_list,
        "page_obj": rows_page,
        "paginator": paginator,
        "per_page": per_page,
        "selected_row": selected_row,
        "product_form": product_form,
        "movement_form": movement_form,
        "query_text": query_text,
        "category_id": category_id,
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


@require_GET
def autocomplete_products(request):
    """API simple que devuelve sugerencias de productos para autocompletar.
    Parámetro: `q` texto de búsqueda (min 1 caracter). Devuelve JSON list de objetos {id_producto, nombre}.
    """
    q = (request.GET.get('q') or '').strip()
    if not q:
        return JsonResponse([], safe=False)

    qs = inventory_queryset(query_text=q)
    suggestions = list(qs.values('id_producto', 'nombre')[:12])
    return JsonResponse(suggestions, safe=False)


@require_POST
@login_required_custom
def quick_update_product(request):
    """API para actualizar rápidamente campos editables de un producto.
    PROTEGIDA CON AUTENTICACIÓN. Espera JSON:
    { "id_producto": "123", "precio_venta": "12.5", "stock_minimo": 5 }
    Retorna JSON con los campos actualizados o error.
    """
    # Validar token CSRF desde header (requerido para AJAX POST)
    from django.middleware.csrf import CsrfViewMiddleware
    csrf_middleware = CsrfViewMiddleware(lambda r: None)
    try:
        csrf_middleware.process_request(request)
    except Exception:
        return JsonResponse({'error': 'CSRF validation failed'}, status=403)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)

    prod_id = str(data.get('id_producto', '')).strip()
    if not prod_id or len(prod_id) > 20:
        return JsonResponse({'error': 'id_producto invalid'}, status=400)

    product = Producto.objects.filter(id_producto=prod_id).first()
    if not product:
        return JsonResponse({'error': 'Product not found'}, status=404)

    updated = {}
    try:
        with transaction.atomic():
            # Validar y actualizar nombre (máx 100 caracteres)
            if 'nombre' in data:
                nombre = str(data['nombre']).strip()[:100]
                if not nombre:
                    return JsonResponse({'error': 'nombre cannot be empty'}, status=400)
                product.nombre = nombre
                updated['nombre'] = product.nombre

            # Validar y actualizar precio_venta (0.01 a 999999.99)
            if 'precio_venta' in data:
                try:
                    precio = float(data['precio_venta'])
                    if not (0.01 <= precio <= 999999.99):
                        return JsonResponse({'error': 'precio_venta must be between 0.01 and 999999.99'}, status=400)
                    product.precio_venta = precio
                    updated['precio_venta'] = product.precio_venta
                except (ValueError, TypeError):
                    return JsonResponse({'error': 'precio_venta must be numeric'}, status=400)

            product.save()

            # Validar y actualizar stock_minimo (0 a 1000000)
            inv, _ = Inventario.objects.get_or_create(id_producto=product)
            if 'stock_minimo' in data:
                try:
                    stock_min = int(data['stock_minimo'])
                    if not (0 <= stock_min <= 1000000):
                        return JsonResponse({'error': 'stock_minimo must be between 0 and 1000000'}, status=400)
                    inv.stock_minimo = stock_min
                    updated['stock_minimo'] = inv.stock_minimo
                except (ValueError, TypeError):
                    return JsonResponse({'error': 'stock_minimo must be integer'}, status=400)

            inv.save()

        return JsonResponse({'ok': True, 'updated': updated})
    except Exception as exc:
        return JsonResponse({'error': 'Server error'}, status=500)


# Acciones POST del inventario

def _save_product(request):
    """
    Crea o actualiza un producto junto con su registro de inventario.
    Si el formulario es inválido, muestra los errores al usuario.
    Usa transacción atómica para garantizar consistencia entre Producto e Inventario.
    """
    data = categories_and_providers()
    categories = data["categories"]
    providers = data["providers"]
    form = ProductForm(request.POST, categories=categories, providers=providers)
    if not form.is_valid():
        messages.error(request, "Revisa los campos del producto antes de guardar.")
        return _render_with_form(request, product_form=form)

    data = form.cleaned_data
    try:
        with transaction.atomic():
            # Actualizar producto existente o crear uno nuevo según product_id
            if data["product_id"]:
                product = Producto.objects.select_for_update().get(pk=data["product_id"])
            else:
                product = Producto()
            product.nombre = data["nombre"]
            product.descripcion = data["descripcion"]
            product.id_categoria_id = data["categoria"]
            product.id_proveedor_id = data["proveedor"] or None
            product.precio_compra = data["precio_compra"]
            product.precio_venta = data["precio_venta"]
            product.unidad_medida = data["unidad_medida"]
            # Asignar fecha de creación solo si es un producto nuevo
            if not product.fecha_creacion:
                product.fecha_creacion = timezone.now()
            product.save()

            # Crear o recuperar el registro de inventario asociado al producto
            inventario, _ = Inventario.objects.get_or_create(id_producto=product)
            inventario.stock_minimo = data["stock_minimo"]
            if inventario.stock_actual is None:
                inventario.stock_actual = 0
            inventario.fecha_actualizacion = timezone.now()
            inventario.save()

        messages.success(request, "Producto guardado correctamente.")
        return redirect(f"{request.path}?product={product.id_producto}")
    except IntegrityError as exc:
        messages.error(request, f"No se pudo guardar el producto: {exc}")
        return _render_with_form(request, product_form=form)


def _delete_product(request):
    """
    Elimina un producto y todos sus datos relacionados (inventario y movimientos).
    Usa transacción atómica para evitar inconsistencias si algún paso falla.
    """
    product_id = (request.POST.get("product_id") or "").strip()
    if not product_id:
        messages.error(request, "Selecciona un producto para eliminar.")
        return redirect(request.path)

    try:
        with transaction.atomic():
            product = Producto.objects.select_for_update().get(pk=product_id)
            # Eliminar inventario y movimientos antes de borrar el producto
            Inventario.objects.filter(id_producto=product).delete()
            MovimientoInventario.objects.filter(id_producto=product).delete()
            product.delete()
        messages.success(request, "Producto eliminado correctamente.")
    except Producto.DoesNotExist:
        messages.error(request, "El producto ya no existe.")
    except IntegrityError:
        messages.error(request, "No se pudo eliminar porque el producto ya tiene referencias en otras tablas.")
    return redirect(request.path)


def _save_movement(request):
    """
    Registra un movimiento de inventario (entrada, salida o ajuste) y actualiza el stock.
    El stock no puede quedar negativo; si lo haría, se lanza un ValueError y se informa al usuario.
    Usa transacción atómica con bloqueo select_for_update para evitar condiciones de carrera.
    """
    form = MovementForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Revisa los campos del movimiento antes de guardar.")
        return _render_with_form(request, movement_form=form)

    data = form.cleaned_data
    product = _resolve_product_from_label(data["producto"])
    if not product:
        messages.error(request, "No se pudo identificar el producto del movimiento.")
        return _render_with_form(request, movement_form=form)

    # Determinar el delta de stock: positivo para entradas, negativo para salidas
    delta = data["cantidad"]
    if data["tipo_movimiento"] in {"salida", "ajuste_salida"}:
        delta = -delta

    try:
        with transaction.atomic():
            inventario, _ = Inventario.objects.select_for_update().get_or_create(id_producto=product)
            actual = inventario.stock_actual or 0
            nuevo = actual + delta
            # Validar que el stock resultante no sea negativo
            if nuevo < 0:
                raise ValueError("El stock no puede quedar en negativo.")
            inventario.stock_actual = nuevo
            if inventario.stock_minimo is None:
                inventario.stock_minimo = 0
            inventario.fecha_actualizacion = timezone.now()
            inventario.save()

            # Crear el registro del movimiento para auditoría
            MovimientoInventario.objects.create(
                id_producto=product,
                id_usuario=_current_user(request),
                tipo_movimiento=data["tipo_movimiento"],
                cantidad=data["cantidad"],
                referencia=f"{data['tipo_movimiento']} - {product.nombre}",
                fecha_movimiento=timezone.now(),
                observaciones=data["observacion"],
            )
        messages.success(request, "Movimiento registrado correctamente.")
        return redirect(f"{request.path}?product={product.id_producto}")
    except ValueError as exc:
        messages.error(request, str(exc))
    except IntegrityError as exc:
        messages.error(request, f"No se pudo registrar el movimiento: {exc}")
    return _render_with_form(request, movement_form=form)


def _resolve_product_from_label(label):
    """
    Resuelve un producto a partir del valor del campo de texto del datalist.
    El valor puede tener el formato "id | nombre" o solo el nombre.
    Retorna el objeto Producto o None si no se encuentra.
    """
    raw = (label or "").strip()
    if not raw:
        return None
    # Intentar extraer el ID numérico del formato "id | nombre"
    token = raw.split("|")[0].strip()
    try:
        product_id = int(token)
    except ValueError:
        # Si no es numérico, buscar por nombre exacto (sin distinguir mayúsculas)
        return Producto.objects.filter(nombre__iexact=raw).first()
    return Producto.objects.filter(id_producto=product_id).first()


def _render_with_form(request, product_form=None, movement_form=None):
    """
    Reconstruye el contexto completo y renderiza la vista de registro con los formularios
    actuales (útil tras un POST fallido para conservar los datos introducidos por el usuario).
    """
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


# Vista de exportación a Excel

@login_required_custom
def export_excel(request):
    """
    Genera y descarga un archivo PDF con dos secciones:
      - 'Inventario': listado completo de productos con su estado de stock.
      - 'Movimientos': hasta 200 movimientos filtrados por producto, tipo y fechas.
    PROTEGIDA: solo usuarios autenticados pueden exportar.
    Nota: la URL y el nombre de la vista se mantienen para compatibilidad; el contenido
    devuelto ahora es PDF y el archivo se nombra con extensión .pdf.
    """
    # Validar y sanitizar parámetros GET
    query_text = (request.GET.get("q") or "").strip()[:100]  # Máx 100 caracteres
    category_id = (request.GET.get("category") or "").strip()
    product_id = (request.GET.get("product") or "").strip()
    movement_type = (request.GET.get("movement_type") or "").strip()
    start_date = _parse_optional_date(request, "from")
    end_date = _parse_optional_date(request, "to")
    # Obtener movimientos filtrados y construir sólo la sección de Movimientos
    movements = report_kpis(
        product_id=product_id,
        movement_type=movement_type,
        start_date=start_date,
        end_date=end_date,
        query_text=query_text,
        category_id=category_id,
    )["movements"]

    buffer = BytesIO()
    # Usar A4 apaisado para dar más espacio horizontal a la tabla
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=18, leftMargin=18, topMargin=18, bottomMargin=18)
    styles = getSampleStyleSheet()
    elements = []

    # Cabecera con estilo similar al PDF de ventas
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

    # Construir PDF en memoria
    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="movimientos_ferreteria.pdf"'
    return response


# Vista de reportes de inventario

@login_required_custom
def reportes(request):
    """
    Vista de reportes del inventario.
    Muestra KPIs de stock, un resumen estadístico y el historial de movimientos
    filtrable por producto, tipo de movimiento y rango de fechas.
    PROTEGIDA: solo usuarios autenticados pueden ver reportes.
    """
    # Validar y sanitizar parámetros GET
    query_text = (request.GET.get("q") or "").strip()[:100]  # Máx 100 caracteres
    category_id = (request.GET.get("category") or "").strip()
    product_id = (request.GET.get("product") or "").strip()
    movement_type = (request.GET.get("movement_type") or "").strip()
    start_date = _parse_optional_date(request, "from")
    end_date = _parse_optional_date(request, "to")

    inv_qs = inventory_queryset(query_text=query_text, category_id=category_id)
    if product_id:
        inv_qs = inv_qs.filter(id_producto=product_id)
    rows = sort_rows(build_rows(inv_qs), "codigo")
    # Resumen con totales de productos por estado de stock
    summary = report_summary(inventory_queryset(query_text=query_text, category_id=category_id))
    # KPIs: total de entradas, salidas y conteo de movimientos en el período filtrado
    kpis = report_kpis(product_id=product_id, movement_type=movement_type, start_date=start_date, end_date=end_date, query_text=query_text, category_id=category_id)

    selected_product = _selected_product_from_request(request)
    if not selected_product and product_id:
        selected_product = Producto.objects.filter(id_producto=product_id).first()

    context = {
        "categories": categories_and_providers()["categories"],
        "rows": rows,
        "summary": summary,
        "movements": kpis["movements"],
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