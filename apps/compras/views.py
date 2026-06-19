import json
import os
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Count, F, Max
from django.http import JsonResponse
from django.http import HttpResponse
from django.shortcuts import render
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.conf import settings

# Generación de PDF con ReportLab
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

from apps.accounts.auth import login_required_custom
from apps.core.models import (
    Compra, DetalleCompra, FacturaProveedor,
    Inventario, MovimientoInventario,
    Producto, Proveedor, Usuario, Categoria,
)

# === Helpers internos ===

def money(x: Decimal) -> Decimal:
    # Redondea a 2 decimales (estilo moneda)
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def _clean(s):
    # Limpia cadenas y evita None
    return (s or "").strip()

def _dec(s, default="0"):
    # Convierte a decimal o retorna None en caso de error
    try:
        return Decimal(str(s if s is not None and str(s).strip() != "" else default))
    except Exception:
        return None

def generar_numero_factura_proveedor() -> str:
    # Genera número de factura incremental diario tipo FP-YYYYMMDD-0001
    hoy = timezone.now().strftime("%Y%m%d")
    pref = f"FP-{hoy}-"
    last = (FacturaProveedor.objects
            .filter(numero_factura__startswith=pref)
            .aggregate(m=Max("numero_factura"))["m"])
    if not last:
        return pref + "0001"
    seq = int(last.split("-")[-1]) + 1
    return pref + str(seq).zfill(4)

# === Vistas HTML principales ===

@login_required_custom
def index(request):
    # Página principal de compras
    return render(request, "compras/index.html")

@login_required_custom
@require_GET
def proveedor(request):
    # Página de proveedores con info y productos por categoría
    proveedores = list(
        Proveedor.objects
        .values(
            "id_proveedor", "nombre", "telefono", "email", "numero_contacto",
            "direccion", "tipo_proveedor", "fecha_registro", "estado",
        )
        .order_by("nombre")
    )
    categorias = (
        Producto.objects
        .values("id_proveedor_id", "id_categoria_id", "id_categoria__nombre")
        .annotate(
            productos=Count("id_producto"),
        )
        .order_by("id_proveedor_id", "id_categoria__nombre")
    )
    categorias_por_proveedor = {}
    for categoria in categorias:
        proveedor_id = categoria["id_proveedor_id"]
        if proveedor_id not in categorias_por_proveedor:
            categorias_por_proveedor[proveedor_id] = []
        categorias_por_proveedor[proveedor_id].append(
            {
                "id_categoria": categoria["id_categoria_id"],
                "nombre": categoria["id_categoria__nombre"] or "Sin categoría",
                "productos": categoria["productos"],
            }
        )
    proveedores_data = []
    for p in proveedores:
        categorias_del_proveedor = categorias_por_proveedor.get(p["id_proveedor"], [])
        p["total_categorias"] = len(categorias_del_proveedor)
        p["total_productos"] = sum(categoria["productos"] for categoria in categorias_del_proveedor)
        # Tomar estado desde la base de datos si existe, si no usar 'Activo' por compatibilidad
        p["estado"] = (p.get("estado") or "Activo")
        proveedores_data.append(
            {
                "proveedor": p,
                "categorias": categorias_del_proveedor,
            }
        )

    # Separar proveedores activos e inactivos para mostrarlos por secciones
    proveedores_activos = [x for x in proveedores_data if (x["proveedor"].get("estado") or "").strip().lower() != "inactivo"]
    proveedores_inactivos = [x for x in proveedores_data if (x["proveedor"].get("estado") or "").strip().lower() == "inactivo"]
    
    # Calcular estadísticas
    total_proveedores = len(proveedores)
    total_productos = Producto.objects.count()
    total_categorias = Categoria.objects.count()
    total_compras = Compra.objects.count()
    
    stats = {
        "total_proveedores": total_proveedores,
        "total_productos": total_productos,
        "total_categorias": total_categorias,
        "total_compras": total_compras,
    }
    
    return render(
        request,
        "compras/proveedor.html",
        {
            "proveedores_data": proveedores_data,
            "proveedores_activos": proveedores_activos,
            "proveedores_inactivos": proveedores_inactivos,
            "stats": stats,
        },
    )

# === APIs principales ===

@login_required_custom
@require_GET
def api_proveedores(request):
# Traemos las instancias de los proveedores activos
    proveedores = Proveedor.objects.exclude(estado__iexact="Inactivo").order_by("nombre")
    
    # Construimos la lista asegurando que id_proveedor sea enviado como un entero puro
    data = [
        {
            "id_proveedor": int(p.id_proveedor),
            "nombre": str(p.nombre),
            "estado": str(p.estado)
        }
        for p in proveedores
    ]
    
    return JsonResponse({"ok": True, "data": data})

@login_required_custom
@require_GET
def api_productos(request):
    # Devuelve productos filtrados por proveedor (param id_proveedor)
    # Incluye stock_actual del inventario
    id_proveedor = request.GET.get("id_proveedor")
    if not id_proveedor:
        return JsonResponse({"ok": False, "error": "Falta id_proveedor"}, status=400)
    qs = (Producto.objects
          .filter(id_proveedor_id=id_proveedor)
          .order_by("nombre")
          .values("id_producto", "nombre", "precio_compra", "precio_venta"))
    
    # Agregar stock_actual de cada producto
    productos = []
    for p in qs:
        inventario = Inventario.objects.filter(id_producto_id=p["id_producto"]).first()
        stock_actual = inventario.stock_actual if inventario else 0
        p["stock_actual"] = stock_actual
        productos.append(p)
    
    return JsonResponse({"ok": True, "data": productos})

@login_required_custom
@require_http_methods(["POST"])
@transaction.atomic
def nueva_compra(request):
    # Registra una compra completa con sus detalles y movimientos de inventario
    id_usuario = request.session.get("id_usuario")
    if not id_usuario:
        return JsonResponse({"ok": False, "error": "Sesión inválida o expirada"}, status=401)
        
    try:
        usuario = Usuario.objects.get(id_usuario=id_usuario)
    except Usuario.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Usuario no encontrado"}, status=404)

    id_proveedor = request.POST.get("id_proveedor")
    items_raw = request.POST.get("items")  # JSON string
    iva_rate_raw = (request.POST.get("iva_rate", "15") or "15").strip()
    
    if not id_proveedor:
        return JsonResponse({"ok": False, "error": "Falta id_proveedor"}, status=400)
    if not items_raw:
        return JsonResponse({"ok": False, "error": "Falta items (JSON)"}, status=400)
        
    try:
        iva_rate = Decimal(iva_rate_raw.replace(",", ""))
    except Exception:
        return JsonResponse({"ok": False, "error": "IVA inválido"}, status=400)
        
    if iva_rate < 0 or iva_rate > 100:
        return JsonResponse({"ok": False, "error": "IVA debe estar entre 0 y 100"}, status=400)
        
    try:
        items = json.loads(items_raw)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "items no es JSON válido"}, status=400)
        
    if not isinstance(items, list) or len(items) == 0:
        return JsonResponse({"ok": False, "error": "items debe ser una lista con al menos 1 producto"}, status=400)
        
    try:
        proveedor = Proveedor.objects.get(id_proveedor=id_proveedor)
    except Proveedor.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Proveedor no encontrado"}, status=404)

    subtotal = Decimal("0.00")
    normalizados = []
    
    for i, it in enumerate(items, start=1):
        try:
            id_producto = int(it["id_producto"])
            cantidad = int(it["cantidad"])
            
            # Limpieza y conversión a Decimal nativo de Python para evitar fallos
            p_compra_str = str(it.get("precio_unitario", "0")).replace(",", "").strip()
            p_venta_str = str(it.get("precio_venta", "0")).replace(",", "").strip()
            
            precio_unitario = Decimal(p_compra_str) if p_compra_str else Decimal("0.00")
            precio_venta = Decimal(p_venta_str) if p_venta_str else Decimal("0.00")
        except Exception:
            return JsonResponse({"ok": False, "error": f"Item #{i}: Formato de precios o cantidades inválido"}, status=400)
            
        if cantidad <= 0:
            return JsonResponse({"ok": False, "error": f"Item #{i}: cantidad debe ser > 0"}, status=400)
        if precio_unitario < 0:
            return JsonResponse({"ok": False, "error": f"Item #{i}: precio_unitario no puede ser negativo"}, status=400)
        if precio_venta < 0:
            return JsonResponse({"ok": False, "error": f"Item #{i}: precio_venta no puede ser negativo"}, status=400)
            
        try:
            producto = Producto.objects.get(id_producto=id_producto)
        except Producto.DoesNotExist:
            return JsonResponse({"ok": False, "error": f"Item #{i}: El producto no existe"}, status=404)

        if producto.id_proveedor_id and int(producto.id_proveedor_id) != int(id_proveedor):
            return JsonResponse(
                {"ok": False, "error": f"El producto '{producto.nombre}' no pertenece al proveedor seleccionado."},
                status=400
            )
            
        # Validar cantidad contra stock_maximo
        inventario = Inventario.objects.filter(id_producto=producto).first()
        stock_maximo = inventario.stock_maximo if inventario else 60
        if cantidad > stock_maximo:
            return JsonResponse({"ok": False, "error": f"Item #{i}: cantidad no puede ser mayor a {stock_maximo}"}, status=400)
            
        if inventario and inventario.stock_actual and inventario.stock_actual >= stock_maximo:
            return JsonResponse(
                {"ok": False, "error": f"No se puede comprar '{producto.nombre}': stock actual ({inventario.stock_actual}) ya alcanzó el máximo de {stock_maximo}."},
                status=400
            )
            
        subtotal += (precio_unitario * cantidad)
        
        # Guardamos los objetos de tipo DECIMAL PUROS (sin llamar a money() aquí)
        normalizados.append({
            "producto": producto,
            "cantidad": cantidad,
            "precio_unitario": precio_unitario,
            "precio_venta": precio_venta,
        })
        
    # Operaciones matemáticas directas con Decimales nativos
    impuesto = subtotal * (iva_rate / Decimal("100"))
    total = subtotal + impuesto
    ahora = timezone.now()
    
    # 1. Crear la Compra Principal aplicando money() de forma segura en la asignación final
    compra = Compra.objects.create(
        id_proveedor=proveedor,
        id_usuario=usuario,
        fecha=ahora,
        total=money(total),
    )
    
    # 2. Registrar los detalles de los productos comprados
    DetalleCompra.objects.bulk_create([
        DetalleCompra(
            id_compra=compra,
            id_producto=x["producto"],
            cantidad=x["cantidad"],
            precio_unitario=money(x["precio_unitario"]),
        )
        for x in normalizados
    ])
    
    # 3. GENERAR UNA ÚNICA FACTURA ASOCIADA A LA COMPRA
    numero_factura = generar_numero_factura_proveedor()
    factura_obj = FacturaProveedor.objects.create(
        id_compra=compra,
        numero_factura=numero_factura,
        tipo_comprobante="FACTURA",
        fecha_emision=ahora.date(),
        subtotal=money(subtotal),
        impuesto=money(impuesto),
        total=money(total),
        estado="APROBADA",
    )
    
    # 4. Actualizar Precios e Inventarios en el Bucle de forma limpia
    movimientos = []
    for x in normalizados:
        producto = x["producto"]
        cantidad = x["cantidad"]
        precio_unitario = x["precio_unitario"]
        precio_venta = x["precio_venta"]
        
        # Pasamos los decimales usando la función money() de forma segura
        Producto.objects.filter(id_producto=producto.id_producto).update(
            precio_compra=money(precio_unitario),
            precio_venta=money(precio_venta),
        )
        
        inv, _ = Inventario.objects.get_or_create(
            id_producto=producto,
            defaults={
                "stock_actual": 0,
                "stock_minimo": 10,
                "stock_maximo": 60,
                "fecha_actualizacion": ahora,
            }
        )
        
        Inventario.objects.filter(id_inventario=inv.id_inventario, stock_actual__isnull=True).update(stock_actual=0)
        Inventario.objects.filter(id_inventario=inv.id_inventario).update(
            stock_actual=F("stock_actual") + cantidad,
            fecha_actualizacion=ahora,
        )
        
        movimientos.append(MovimientoInventario(
            id_producto=producto,
            id_usuario=usuario,
            tipo_movimiento="Entrada",
            cantidad=cantidad,
            referencia=f"Entrada:{compra.id_compra}",
            fecha_movimiento=ahora,
            observaciones=f"Entrada por compra. Factura {numero_factura}. Proveedor {proveedor.nombre}. IVA {iva_rate}%.",
        ))
        
    # 5. Guardar los movimientos de inventario en masa
    MovimientoInventario.objects.bulk_create(movimientos)
    
    # 6. Responder de forma exitosa convirtiendo a String los valores numéricos purificados
    return JsonResponse({
        "ok": True,
        "id_compra": compra.id_compra,
        "numero_factura": numero_factura,
        "id_factura": factura_obj.pk,  
        "iva_rate": str(money(iva_rate)),
        "subtotal": str(money(subtotal)),
        "impuesto": str(money(impuesto)),
        "total": str(money(total)),
    })
# === APIs de gestión rápida (modal) ===

@login_required_custom
@require_POST
@transaction.atomic
def api_proveedor_upsert(request):
    # Crear o actualizar proveedor
    nombre = _clean(request.POST.get("nombre"))
    telefono = _clean(request.POST.get("telefono"))
    email = _clean(request.POST.get("email"))
    numero_contacto = _clean(request.POST.get("numero_contacto"))
    direccion = _clean(request.POST.get("direccion"))
    tipo_proveedor = _clean(request.POST.get("tipo_proveedor"))
    estado = _clean(request.POST.get("estado"))
    if not nombre:
        return JsonResponse({"ok": False, "error": "El nombre del proveedor es requerido."}, status=400)
    proveedor = Proveedor.objects.filter(nombre__iexact=nombre).first()
    if proveedor:
        changed = False
        if telefono and proveedor.telefono != telefono:
            proveedor.telefono = telefono; changed = True
        if email and proveedor.email != email:
            proveedor.email = email; changed = True
        if numero_contacto and proveedor.numero_contacto != numero_contacto:
            proveedor.numero_contacto = numero_contacto; changed = True
        if direccion and proveedor.direccion != direccion:
            proveedor.direccion = direccion; changed = True
        if tipo_proveedor and proveedor.tipo_proveedor != tipo_proveedor:
            proveedor.tipo_proveedor = tipo_proveedor; changed = True
        if estado and (proveedor.estado or "") != estado:
            proveedor.estado = estado; changed = True
        if changed:
            proveedor.save()
        return JsonResponse({"ok": True, "data": {"id_proveedor": proveedor.id_proveedor, "nombre": proveedor.nombre, "created": False}})
    proveedor = Proveedor.objects.create(
        nombre=nombre,
        telefono=telefono or None,
        email=email or None,
        numero_contacto=numero_contacto or None,
        direccion=direccion or None,
        tipo_proveedor=tipo_proveedor or None,
        estado=estado or None,
        fecha_registro=timezone.now(),
    )
    return JsonResponse({"ok": True, "data": {"id_proveedor": proveedor.id_proveedor, "nombre": proveedor.nombre, "created": True}})

@login_required_custom
@require_POST
@transaction.atomic
def api_proveedor_actualizar(request):
    # Actualiza proveedor existente por ID
    id_proveedor = _clean(request.POST.get("id_proveedor"))
    nombre = _clean(request.POST.get("nombre"))
    telefono = _clean(request.POST.get("telefono"))
    email = _clean(request.POST.get("email"))
    numero_contacto = _clean(request.POST.get("numero_contacto"))
    direccion = _clean(request.POST.get("direccion"))
    tipo_proveedor = _clean(request.POST.get("tipo_proveedor"))
    estado = _clean(request.POST.get("estado"))

    if not id_proveedor:
        return JsonResponse({"ok": False, "error": "Falta id_proveedor."}, status=400)
    if not nombre:
        return JsonResponse({"ok": False, "error": "El nombre del proveedor es requerido."}, status=400)

    proveedor = Proveedor.objects.filter(id_proveedor=id_proveedor).first()
    if not proveedor:
        return JsonResponse({"ok": False, "error": "Proveedor no encontrado."}, status=404)

    nombre_duplicado = (
        Proveedor.objects
        .filter(nombre__iexact=nombre)
        .exclude(id_proveedor=proveedor.id_proveedor)
        .exists()
    )
    if nombre_duplicado:
        return JsonResponse({"ok": False, "error": "Ya existe otro proveedor con ese nombre."}, status=409)

    proveedor.nombre = nombre
    proveedor.telefono = telefono or None
    proveedor.email = email or None
    proveedor.numero_contacto = numero_contacto or None
    proveedor.direccion = direccion or None
    proveedor.tipo_proveedor = tipo_proveedor or None
    proveedor.estado = estado or None
    proveedor.save()

    return JsonResponse({
        "ok": True,
        "data": {
            "id_proveedor": proveedor.id_proveedor,
            "nombre": proveedor.nombre,
        }
    })

@login_required_custom
@require_POST
@transaction.atomic
def api_categoria_upsert(request):
    # Crear o actualizar categoría
    nombre = _clean(request.POST.get("nombre"))
    descripcion = _clean(request.POST.get("descripcion"))
    if not nombre:
        return JsonResponse({"ok": False, "error": "El nombre de la categoría es requerido."}, status=400)
    categoria = Categoria.objects.filter(nombre__iexact=nombre).first()
    if categoria:
        if descripcion and (categoria.descripcion or "") != descripcion:
            categoria.descripcion = descripcion
            categoria.save()
        return JsonResponse({"ok": True, "data": {"id_categoria": categoria.id_categoria, "nombre": categoria.nombre, "created": False}})
    categoria = Categoria.objects.create(
        nombre=nombre,
        descripcion=descripcion or None,
        fecha_creacion=timezone.now(),
    )
    return JsonResponse({"ok": True, "data": {"id_categoria": categoria.id_categoria, "nombre": categoria.nombre, "created": True}})

@login_required_custom
@require_GET
def api_categorias_buscar(request):
    # Buscar categorías por nombre para autocompletar
    q = (request.GET.get("q") or "").strip()
    if not q:
        return JsonResponse({"ok": True, "data": []})

    qs = (
        Categoria.objects
        .filter(nombre__icontains=q)
        .order_by("nombre")
        .values("id_categoria", "nombre", "descripcion")[:12]
    )
    return JsonResponse({"ok": True, "data": list(qs)})

@login_required_custom
@require_POST
@transaction.atomic
def api_producto_crear(request):
    # Crear producto para proveedor y categoría (validando duplicados)
    id_proveedor = _clean(request.POST.get("id_proveedor"))
    id_categoria = _clean(request.POST.get("id_categoria"))
    nombre = _clean(request.POST.get("nombre"))
    descripcion = _clean(request.POST.get("descripcion"))
    unidad_medida = _clean(request.POST.get("unidad_medida"))
    precio_compra = _dec(request.POST.get("precio_compra"), "0")
    precio_venta = _dec(request.POST.get("precio_venta"), "0")
    stock_maximo = request.POST.get("stock_maximo", "60")
    try:
        stock_maximo = int(stock_maximo) if stock_maximo else 60
    except (ValueError, TypeError):
        stock_maximo = 60
    
    if not id_proveedor:
        return JsonResponse({"ok": False, "error": "Falta proveedor."}, status=400)
    if not id_categoria:
        return JsonResponse({"ok": False, "error": "Falta categoría."}, status=400)
    if not nombre:
        return JsonResponse({"ok": False, "error": "El nombre del producto es requerido."}, status=400)
    if precio_compra is None or precio_venta is None:
        return JsonResponse({"ok": False, "error": "Precios inválidos."}, status=400)
    if precio_compra < 0 or precio_venta < 0:
        return JsonResponse({"ok": False, "error": "Los precios no pueden ser negativos."}, status=400)
    dup = Producto.objects.filter(id_proveedor_id=id_proveedor, nombre__iexact=nombre).first()
    if dup:
        return JsonResponse({"ok": False, "error": "Ya existe un producto con ese nombre para este proveedor."}, status=409)
    producto = Producto.objects.create(
        id_proveedor_id=int(id_proveedor),
        id_categoria_id=int(id_categoria),
        nombre=nombre,
        descripcion=descripcion or None,
        precio_compra=money(precio_compra),
        precio_venta=money(precio_venta),
        unidad_medida=unidad_medida or None,
        fecha_creacion=timezone.now(),
    )
    Inventario.objects.get_or_create(
        id_producto=producto,
        defaults={
            "stock_actual": 0,
            "stock_minimo": 10,
            "stock_maximo": stock_maximo,
            "fecha_actualizacion": timezone.now(),
        }
    )
    return JsonResponse({
        "ok": True,
        "data": {
            "id_producto": producto.id_producto,
            "nombre": producto.nombre,
            "precio_compra": str(producto.precio_compra or "0.00"),
            "precio_venta": str(producto.precio_venta or "0.00"),
            "id_proveedor": int(id_proveedor),
            "id_categoria": int(id_categoria),
        }
    })

# === API: Autocompletar proveedores ===

@login_required_custom
@require_GET
def api_proveedores_buscar(request):
    # Buscar proveedores por nombre para autocompletar
    q = (request.GET.get("q") or "").strip()
    if not q:
        return JsonResponse({"ok": True, "data": []})
    qs = (Proveedor.objects
          .exclude(estado__iexact="Inactivo")
          .filter(nombre__icontains=q)
          .order_by("nombre")
          .values(
              "id_proveedor", "nombre",
              "telefono", "email",
              "numero_contacto", "direccion",
              "tipo_proveedor", "estado",
          )[:12])
    return JsonResponse({"ok": True, "data": list(qs)})

# Generando PDF de factura de compra con ReportLab
@login_required_custom
def generar_factura_pdf(request, factura_id):
    # Buscamos la factura del proveedor usando el campo correcto de tu base de datos: id_factura_proveedor
    factura = get_object_or_404(
        FacturaProveedor.objects.select_related('id_compra__id_proveedor'),
        id_factura_proveedor=factura_id
    )

    compra = factura.id_compra
    proveedor = compra.id_proveedor

    # Obtenemos los detalles de los productos incluidos en esta compra
    detalles = DetalleCompra.objects.filter(
        id_compra=compra
    ).select_related('id_producto')

    # Configuración de la respuesta HTTP para mostrar en el navegador web
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = (
        f'inline; filename="Factura_{factura.numero_factura}.pdf"'
    )

    # Inicialización del objeto canvas en formato A4 destinado a la web
    pdf = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    azul = colors.HexColor("#0B4EA2")

    # Definimos la ruta del logo
    logo = os.path.join(settings.BASE_DIR, "static", "assets", "Ferreteria.png")

    # =========================================================================
    # 1. RENDERIZAR EL PDF EN VIVO PARA EL NAVEGADOR DEL USUARIO
    # =========================================================================
    _dibujar_contenido_pdf(pdf, factura, proveedor, detalles, width, height, azul, logo)
    pdf.showPage()
    pdf.save()

    # 2. RESPALDO AUTOMÁTICO TRAS BAMBALINAS EN EL DISCO DURO LOCAL
    try:
        # Obtenemos la ruta física de la carpeta "Compras" mapeada en settings
        ruta_compras = settings.SUBCARPETAS_FERRETERIA.get("Compras")
        if ruta_compras:
            nombre_archivo_local = f"Factura_{factura.numero_factura}.pdf"
            ruta_completa_archivo = os.path.join(ruta_compras, nombre_archivo_local)
            
            # Inicializamos un segundo canvas que apunta directamente al archivo en el disco duro
            pdf_local = canvas.Canvas(ruta_completa_archivo, pagesize=A4)
            
            # Reutilizamos la función de dibujo para estampar exactamente los mismos datos
            _dibujar_contenido_pdf(pdf_local, factura, proveedor, detalles, width, height, azul, logo)
            pdf_local.showPage()
            pdf_local.save()
            print(f"[RESPALDO AUTOMÁTICO] Copia guardada físicamente en: {ruta_completa_archivo}")
    except Exception as e:
        # Si falla por un tema de permisos del sistema operativo, el servidor avisa en la terminal,
        print(f"[ALERTA RESPALDO] No se pudo guardar la copia local en disco duro. Motivo: {e}")
    
    return response


def _dibujar_contenido_pdf(pdf, factura, proveedor, detalles, width, height, azul, logo):
    """ Función auxiliar encargada exclusivamente de trazar la interfaz gráfica del comprobante """
    # --- LOGO ---
    if os.path.exists(logo):
        pdf.drawImage(logo, 20, height - 180, width=290, height=180, preserveAspectRatio=True)

    # --- RECUADRO DE FACTURA Y FECHA ---
    pdf.setLineWidth(1)
    pdf.setStrokeColor(azul)
    pdf.rect(400, height - 90, 155, 30)
    pdf.rect(400, height - 120, 155, 30)

    # Fuente ajustada a 8 para evitar el desborde visual del código de la factura
    pdf.setFont("Helvetica-Bold", 8)
    pdf.setFillColor(colors.black)
    pdf.drawString(405, height - 72, f"FACTURA PROV N°: {factura.numero_factura}")
    pdf.drawString(405, height - 102, f"FECHA: {factura.fecha_emision.strftime('%d/%m/%Y')}")

    # --- DATOS DE LA EMPRESA ---
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, height - 180, "DATOS DE LA EMPRESA")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, height - 198, "Dirección: Granada Diriomo, de la entrada principal")
    pdf.drawString(40, height - 212, " de Diriomo una cuadra al Norte a mano izquierda")
    pdf.drawString(40, height - 226, "Teléfono: +505 8765-4321")
    pdf.drawString(40, height - 240, "RUC/NIT: J-12345678-9")
    pdf.drawString(40, height - 254, "Email: admin.ferreteria@gmail.com")

    # --- DATOS DEL PROVEEDOR ---
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, height - 285, "DATOS DEL PROVEEDOR")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, height - 305, f"Razon Social: {proveedor.nombre}")
    pdf.drawString(40, height - 319, f"Teléfono: {proveedor.telefono or 'N/A'}")
    pdf.drawString(40, height - 333, f"Email: {proveedor.email or 'N/A'}")
    pdf.drawString(40, height - 347, f"Contacto: {proveedor.numero_contacto or 'N/A'}")
    pdf.drawString(40, height - 361, f"Dirección: {proveedor.direccion or 'N/A'}")

    # --- CABECERA DE LA TABLA ---
    y = height - 400
    pdf.setFillColor(azul)
    pdf.rect(40, y, width - 80, 20, fill=True, stroke=False)
    
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(45, y + 5, "Descripción del Producto")
    pdf.drawRightString(320, y + 5, "Cant.")
    pdf.drawRightString(430, y + 5, "Precio U.")
    pdf.drawRightString(550, y + 5, "Subtotal")

    # --- CUERPO DE LA TABLA ---
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica", 10)
    
    for detalle in detalles:
        y -= 20
        if y < 80:
            pdf.showPage()
            y = height - 60
            pdf.setFont("Helvetica", 10)

        cant = detalle.cantidad
        p_uni = detalle.precio_unitario
        subtotal_item = cant * p_uni

        pdf.drawString(45, y + 4, detalle.id_producto.nombre)
        pdf.drawRightString(320, y + 4, str(cant))
        pdf.drawRightString(430, y + 4, f"C$ {p_uni:,.2f}")
        pdf.drawRightString(550, y + 4, f"C$ {subtotal_item:,.2f}")
        
        pdf.setStrokeColor(colors.lightgrey)
        pdf.setLineWidth(0.5)
        pdf.line(40, y, width - 40, y)

    # --- TOTALES FINALES ---
    y -= 30
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawRightString(430, y, "Subtotal:")
    pdf.drawRightString(550, y, f"C$ {factura.subtotal:,.2f}")
    
    y -= 15
    pdf.drawRightString(430, y, "Impuesto (IVA):")
    pdf.drawRightString(550, y, f"C$ {factura.impuesto:,.2f}")
    
    y -= 20
    pdf.setStrokeColor(azul)
    pdf.setLineWidth(1)
    pdf.line(350, y + 15, width - 40, y + 15)

    pdf.setFont("Helvetica-Bold", 11)
    pdf.setFillColor(azul)
    pdf.drawRightString(430, y, "TOTAL COMPRA:")
    pdf.drawRightString(550, y, f"C$ {factura.total:,.2f}")