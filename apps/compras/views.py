"""
views.py (módulo Compras)

Este archivo contiene:
- Vistas HTML (render del template principal de compras)
- Endpoints API para:
  - listar proveedores
  - listar productos por proveedor
  - registrar una compra (con detalle, factura, inventario y movimiento)
  - upsert de proveedor (crear o reutilizar por nombre)
  - upsert de categoría (crear o reutilizar por nombre)
  - crear producto (y asegurar inventario inicial = 0)
  - buscar proveedores (autocomplete)
"""

import json
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import F, Max, Q, Sum, Value, IntegerField
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.auth import login_required_custom
from apps.core.models import (
    Compra, DetalleCompra, FacturaProveedor,
    Inventario, MovimientoInventario,
    Producto, Proveedor, Usuario, Categoria,
)


# Helpers de formato / limpieza / decimal

def money(x: Decimal) -> Decimal:
    """
    Redondea a 2 decimales (moneda) con ROUND_HALF_UP (estilo contable).
    Esto asegura que todo lo guardado en DB mantenga el mismo formato.
    """
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _clean(s):
    """Quita espacios y evita None. Útil para campos de texto del request.POST."""
    return (s or "").strip()


def _dec(s, default="0"):
    """
    Convierte un valor (string o número) a Decimal.
    Si el valor viene vacío/None, usa 'default'.
    Si no puede convertir, devuelve None (para validar y responder error).
    """
    try:
        return Decimal(str(s if s is not None and str(s).strip() != "" else default))
    except Exception:
        return None


# Generación de número de factura interno

def generar_numero_factura_proveedor() -> str:
    """
    Genera un consecutivo interno por día para FacturaProveedor:

      FP-YYYYMMDD-0001
      FP-YYYYMMDD-0002
      ...

    Lógica:
    - Se obtiene el prefijo del día (FP-YYYYMMDD-)
    - Se busca el último número de factura del día con ese prefijo
    - Si no existe, empieza en 0001
    - Si existe, incrementa la secuencia en 1
    """
    hoy = timezone.now().strftime("%Y%m%d")
    pref = f"FP-{hoy}-"

    last = (FacturaProveedor.objects
            .filter(numero_factura__startswith=pref)
            .aggregate(m=Max("numero_factura"))["m"])

    if not last:
        return pref + "0001"

    seq = int(last.split("-")[-1]) + 1
    return pref + str(seq).zfill(4)


# Vista HTML principal

@login_required_custom
def index(request):
    """
    Renderiza el template principal del módulo Compras.
    Este template carga el JS y CSS necesarios para operar la compra.
    """
    return render(request, "compras/index.html")


@login_required_custom
@require_GET
def proveedor(request):
    """
    Vista de consulta por proveedor.

    Muestra cada proveedor con sus productos y el total de movimientos
    de inventario de tipo Entrada y Salida por producto.
    """
    proveedores = list(
        Proveedor.objects
        .values("id_proveedor", "nombre")
        .order_by("nombre")
    )

    productos = (
        Producto.objects
        .values("id_producto", "id_proveedor_id", "nombre")
        .annotate(
            entradas=Coalesce(
                Sum(
                    "movimientoinventario__cantidad",
                    filter=Q(movimientoinventario__tipo_movimiento__iexact="Entrada"),
                ),
                Value(0),
                output_field=IntegerField(),
            ),
            salidas=Coalesce(
                Sum(
                    "movimientoinventario__cantidad",
                    filter=Q(movimientoinventario__tipo_movimiento__iexact="Salida"),
                ),
                Value(0),
                output_field=IntegerField(),
            ),
        )
        .order_by("id_proveedor_id", "nombre")
    )

    productos_por_proveedor = {}
    for producto in productos:
        proveedor_id = producto["id_proveedor_id"]
        if proveedor_id not in productos_por_proveedor:
            productos_por_proveedor[proveedor_id] = []
        productos_por_proveedor[proveedor_id].append(producto)

    proveedores_data = []
    for p in proveedores:
        productos_del_proveedor = productos_por_proveedor.get(p["id_proveedor"], [])
        p["total_productos"] = len(productos_del_proveedor)
        proveedores_data.append(
            {
                "proveedor": p,
                "productos": productos_del_proveedor,
            }
        )

    return render(
        request,
        "compras/proveedor.html",
        {
            "proveedores_data": proveedores_data,
        },
    )


# APIs: Proveedores y Productos

@login_required_custom
@require_GET
def api_proveedores(request):
    """
    Devuelve la lista de proveedores para llenar el <select> principal.

    Respuesta:
      { ok: true, data: [{id_proveedor, nombre}, ...] }
    """
    proveedores = Proveedor.objects.all().order_by("nombre").values(
        "id_proveedor", "nombre"
    )
    return JsonResponse({"ok": True, "data": list(proveedores)})


@login_required_custom
@require_GET
def api_productos(request):
    """
    Devuelve productos filtrados por proveedor.
    Se usa cuando se selecciona un proveedor en el frontend.

    Parámetros (query string):
      - id_proveedor

    Respuesta:
      { ok: true, data: [{id_producto, nombre, precio_compra, precio_venta}, ...] }
    """
    id_proveedor = request.GET.get("id_proveedor")
    if not id_proveedor:
        return JsonResponse({"ok": False, "error": "Falta id_proveedor"}, status=400)

    qs = (Producto.objects
          .filter(id_proveedor_id=id_proveedor)
          .order_by("nombre")
          .values("id_producto", "nombre", "precio_compra", "precio_venta"))

    return JsonResponse({"ok": True, "data": list(qs)})


# API: Registrar una compra

@login_required_custom
@require_http_methods(["POST"])
@transaction.atomic
def nueva_compra(request):
    """
    Registra una compra completa.

    Flujo general (atómico por transaction.atomic):
    1) Validar proveedor e items
    2) Calcular subtotal/IVA/total
    3) Crear Compra (encabezado)
    4) Crear DetalleCompra (líneas)
    5) Crear FacturaProveedor (factura interna)
    6) Actualizar inventario (stock_actual += cantidad)
    7) Crear MovimientoInventario por cada item
    8) Actualizar Producto.precio_compra con el último precio utilizado (precio más reciente)

    Importante:
    - El frontend siempre manda valores en NIO (C$) para guardar.
    """
    # 1) Usuario autenticado desde sesión
    id_usuario = request.session["id_usuario"]
    usuario = Usuario.objects.get(id_usuario=id_usuario)

    # 2) Datos base POST
    id_proveedor = request.POST.get("id_proveedor")
    items_raw = request.POST.get("items")  # JSON string
    iva_rate_raw = (request.POST.get("iva_rate", "15") or "15").strip()

    if not id_proveedor:
        return JsonResponse({"ok": False, "error": "Falta id_proveedor"}, status=400)
    if not items_raw:
        return JsonResponse({"ok": False, "error": "Falta items (JSON)"}, status=400)

    # 3) IVA manual: validación y rango
    try:
        iva_rate = Decimal(iva_rate_raw)
    except Exception:
        return JsonResponse({"ok": False, "error": "IVA inválido"}, status=400)

    if iva_rate < 0 or iva_rate > 100:
        return JsonResponse({"ok": False, "error": "IVA debe estar entre 0 y 100"}, status=400)

    # 4) Parse de items (JSON)
    try:
        items = json.loads(items_raw)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "items no es JSON válido"}, status=400)

    if not isinstance(items, list) or len(items) == 0:
        return JsonResponse({"ok": False, "error": "items debe ser una lista con al menos 1 producto"}, status=400)

    proveedor = Proveedor.objects.get(id_proveedor=id_proveedor)

    # 5) Normalización/validación de items y cálculo de subtotal
    subtotal = Decimal("0.00")
    normalizados = []

    for i, it in enumerate(items, start=1):
        # Validación de estructura del item
        try:
            id_producto = int(it["id_producto"])
            cantidad = int(it["cantidad"])
            precio_unitario = Decimal(str(it["precio_unitario"]))
        except Exception:
            return JsonResponse({"ok": False, "error": f"Item #{i} inválido"}, status=400)

        # Validación de valores
        if cantidad <= 0:
            return JsonResponse({"ok": False, "error": f"Item #{i}: cantidad debe ser > 0"}, status=400)
        if precio_unitario < 0:
            return JsonResponse({"ok": False, "error": f"Item #{i}: precio_unitario inválido"}, status=400)

        # Producto real desde DB
        producto = Producto.objects.get(id_producto=id_producto)

        # Seguridad: el producto debe pertenecer al proveedor seleccionado
        if producto.id_proveedor_id and int(producto.id_proveedor_id) != int(id_proveedor):
            return JsonResponse(
                {"ok": False, "error": f"El producto '{producto.nombre}' no pertenece al proveedor seleccionado."},
                status=400
            )

        # Acumular subtotal
        subtotal += (precio_unitario * cantidad)

        # Guardar item normalizado (con redondeo contable a 2 decimales)
        normalizados.append({
            "producto": producto,
            "cantidad": cantidad,
            "precio_unitario": money(precio_unitario),
        })

    # 6) Calcular totales (subtotal, impuesto, total)
    subtotal = money(subtotal)
    impuesto = money(subtotal * (iva_rate / Decimal("100")))
    total = money(subtotal + impuesto)
    ahora = timezone.now()

    # 7) Crear Compra (encabezado)
    compra = Compra.objects.create(
        id_proveedor=proveedor,
        id_usuario=usuario,
        fecha=ahora,
        total=total,
    )

    # 8) Crear DetalleCompra (líneas)
    DetalleCompra.objects.bulk_create([
        DetalleCompra(
            id_compra=compra,
            id_producto=x["producto"],
            cantidad=x["cantidad"],
            precio_unitario=x["precio_unitario"],
        )
        for x in normalizados
    ])

    # 9) Crear FacturaProveedor (interno)
    numero_factura = generar_numero_factura_proveedor()

    FacturaProveedor.objects.create(
        id_compra=compra,
        numero_factura=numero_factura,
        tipo_comprobante="FACTURA",
        fecha_emision=ahora.date(),
        subtotal=subtotal,
        impuesto=impuesto,
        total=total,
        estado="APROBADA",
    )

    # 10) Inventario + Movimientos + actualización de último precio
    movimientos = []

    for x in normalizados:
        producto = x["producto"]
        cantidad = x["cantidad"]
        precio_unitario = x["precio_unitario"]

        # (A) Guardar el último precio de compra usado para el producto.
        # Esto permite que el frontend muestre el precio de compra más reciente
        # cuando se seleccione el producto en compras.
        Producto.objects.filter(id_producto=producto.id_producto).update(
            precio_compra=precio_unitario
        )

        # (B) Asegurar que exista Inventario para el producto.
        inv, _ = Inventario.objects.get_or_create(
            id_producto=producto,
            defaults={
                "stock_actual": 0,
                "stock_minimo": 0,
                "stock_maximo": 0,
                "fecha_actualizacion": ahora,
            }
        )

        # Normaliza NULL -> 0 si stock_actual estaba en NULL en DB
        Inventario.objects.filter(id_inventario=inv.id_inventario, stock_actual__isnull=True).update(stock_actual=0)

        # (C) Sumar stock de la compra
        Inventario.objects.filter(id_inventario=inv.id_inventario).update(
            stock_actual=F("stock_actual") + cantidad,
            fecha_actualizacion=ahora,
        )

        # (D) Registrar movimiento de inventario (auditoría)
        movimientos.append(MovimientoInventario(
            id_producto=producto,
            id_usuario=usuario,
            tipo_movimiento="Entrada",
            cantidad=cantidad,
            referencia=f"Entrada:{compra.id_compra}",
            fecha_movimiento=ahora,
            observaciones=f"Entrada por compra. Factura {numero_factura}. Proveedor {proveedor.nombre}. IVA {iva_rate}%.",
        ))

    # Inserción masiva de movimientos
    MovimientoInventario.objects.bulk_create(movimientos)

    # 11) Respuesta al frontend
    return JsonResponse({
        "ok": True,
        "id_compra": compra.id_compra,
        "numero_factura": numero_factura,
        "iva_rate": str(iva_rate),
        "subtotal": str(subtotal),
        "impuesto": str(impuesto),
        "total": str(total),
    })


# APIs: Modal "Nuevo producto"
@login_required_custom
@require_POST
@transaction.atomic
def api_proveedor_upsert(request):
    """
    Crea o reutiliza un proveedor basado en el nombre.

    - Si existe: actualiza campos SOLO si vienen valores y son distintos.
    - Si no existe: crea proveedor nuevo.
    """
    nombre = _clean(request.POST.get("nombre"))
    telefono = _clean(request.POST.get("telefono"))
    email = _clean(request.POST.get("email"))
    numero_contacto = _clean(request.POST.get("numero_contacto"))
    direccion = _clean(request.POST.get("direccion"))
    tipo_proveedor = _clean(request.POST.get("tipo_proveedor"))

    if not nombre:
        return JsonResponse({"ok": False, "error": "El nombre del proveedor es requerido."}, status=400)

    proveedor = Proveedor.objects.filter(nombre__iexact=nombre).first()

    if proveedor:
        # Si ya existe, solo actualizamos los campos si el usuario mandó valores nuevos
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
        fecha_registro=timezone.now(),
    )

    return JsonResponse({"ok": True, "data": {"id_proveedor": proveedor.id_proveedor, "nombre": proveedor.nombre, "created": True}})


@login_required_custom
@require_POST
@transaction.atomic
def api_categoria_upsert(request):
    """
    Crea o reutiliza una categoría basada en el nombre.

    - Si existe: actualiza la descripción si viene una nueva.
    - Si no existe: crea una nueva.
    """
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
@require_POST
@transaction.atomic
def api_producto_crear(request):
    """
    Crea un producto nuevo para un proveedor y una categoría.

    Reglas:
    - Valida proveedor, categoría, nombre y precios
    - Evita duplicado por nombre dentro del mismo proveedor
    - Crea producto con precio_compra/precio_venta iniciales
    - Asegura Inventario con stock_actual = 0 (Opción B)
    """
    id_proveedor = _clean(request.POST.get("id_proveedor"))
    id_categoria = _clean(request.POST.get("id_categoria"))
    nombre = _clean(request.POST.get("nombre"))
    descripcion = _clean(request.POST.get("descripcion"))
    unidad_medida = _clean(request.POST.get("unidad_medida"))

    precio_compra = _dec(request.POST.get("precio_compra"), "0")
    precio_venta = _dec(request.POST.get("precio_venta"), "0")

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

    # Evitar duplicado por nombre dentro del mismo proveedor
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

    # Asegurar inventario en 0 (no se incrementa hasta una compra)
    Inventario.objects.get_or_create(
        id_producto=producto,
        defaults={
            "stock_actual": 0,
            "stock_minimo": 0,
            "stock_maximo": 0,
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


# API: Buscar proveedores (autocomplete)
@login_required_custom
@require_GET
def api_proveedores_buscar(request):
    """
    Autocomplete para proveedores por nombre.

    Parámetros:
      - q: texto a buscar

    Respuesta:
      { ok: true, data: [proveedor...] }

    Se devuelven campos extra para poder rellenar automáticamente el formulario del modal.
    """
    q = (request.GET.get("q") or "").strip()

    if not q:
        return JsonResponse({"ok": True, "data": []})

    qs = (Proveedor.objects
          .filter(nombre__icontains=q)
          .order_by("nombre")
          .values(
              "id_proveedor", "nombre",
              "telefono", "email",
              "numero_contacto", "direccion",
              "tipo_proveedor"
          )[:12])

    return JsonResponse({"ok": True, "data": list(qs)})