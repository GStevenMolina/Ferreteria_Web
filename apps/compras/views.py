import json
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import F, Max
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


def money(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _clean(s):
    return (s or "").strip()


def _dec(s, default="0"):
    try:
        return Decimal(str(s if s is not None and str(s).strip() != "" else default))
    except Exception:
        return None


def generar_numero_factura_proveedor() -> str:
    """
    Consecutivo interno por día:
      FP-YYYYMMDD-0001, FP-YYYYMMDD-0002, ...
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


@login_required_custom
def index(request):
    return render(request, "compras/index.html")


@login_required_custom
@require_GET
def api_proveedores(request):
    proveedores = Proveedor.objects.all().order_by("nombre").values(
        "id_proveedor", "nombre"
    )
    return JsonResponse({"ok": True, "data": list(proveedores)})


@login_required_custom
@require_GET
def api_productos(request):
    """
    Productos filtrados por proveedor. Incluye precios compra/venta.
    """
    id_proveedor = request.GET.get("id_proveedor")
    if not id_proveedor:
        return JsonResponse({"ok": False, "error": "Falta id_proveedor"}, status=400)

    qs = (Producto.objects
          .filter(id_proveedor_id=id_proveedor)
          .order_by("nombre")
          .values("id_producto", "nombre", "precio_compra", "precio_venta"))

    return JsonResponse({"ok": True, "data": list(qs)})


@login_required_custom
@require_http_methods(["POST"])
@transaction.atomic
def nueva_compra(request):
    # Usuario desde sesión
    id_usuario = request.session["id_usuario"]
    usuario = Usuario.objects.get(id_usuario=id_usuario)

    # Datos base
    id_proveedor = request.POST.get("id_proveedor")
    items_raw = request.POST.get("items")  # JSON string
    iva_rate_raw = (request.POST.get("iva_rate", "15") or "15").strip()

    if not id_proveedor:
        return JsonResponse({"ok": False, "error": "Falta id_proveedor"}, status=400)
    if not items_raw:
        return JsonResponse({"ok": False, "error": "Falta items (JSON)"}, status=400)

    # IVA manual
    try:
        iva_rate = Decimal(iva_rate_raw)
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

    proveedor = Proveedor.objects.get(id_proveedor=id_proveedor)

    # Calcular subtotal y validar items
    subtotal = Decimal("0.00")
    normalizados = []

    for i, it in enumerate(items, start=1):
        try:
            id_producto = int(it["id_producto"])
            cantidad = int(it["cantidad"])
            precio_unitario = Decimal(str(it["precio_unitario"]))
        except Exception:
            return JsonResponse({"ok": False, "error": f"Item #{i} inválido"}, status=400)

        if cantidad <= 0:
            return JsonResponse({"ok": False, "error": f"Item #{i}: cantidad debe ser > 0"}, status=400)
        if precio_unitario < 0:
            return JsonResponse({"ok": False, "error": f"Item #{i}: precio_unitario inválido"}, status=400)

        producto = Producto.objects.get(id_producto=id_producto)

        # Seguridad: que el producto pertenezca al proveedor seleccionado
        if producto.id_proveedor_id and int(producto.id_proveedor_id) != int(id_proveedor):
            return JsonResponse(
                {"ok": False, "error": f"El producto '{producto.nombre}' no pertenece al proveedor seleccionado."},
                status=400
            )

        subtotal += (precio_unitario * cantidad)

        normalizados.append({
            "producto": producto,
            "cantidad": cantidad,
            "precio_unitario": money(precio_unitario),
        })

    subtotal = money(subtotal)
    impuesto = money(subtotal * (iva_rate / Decimal("100")))
    total = money(subtotal + impuesto)
    ahora = timezone.now()

    # Encabezado Compra
    compra = Compra.objects.create(
        id_proveedor=proveedor,
        id_usuario=usuario,
        fecha=ahora,
        total=total,
    )

    # Detalle
    DetalleCompra.objects.bulk_create([
        DetalleCompra(
            id_compra=compra,
            id_producto=x["producto"],
            cantidad=x["cantidad"],
            precio_unitario=x["precio_unitario"],
        )
        for x in normalizados
    ])

    # FacturaProveedor (número interno automático)
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

    # Inventario + Movimiento
    movimientos = []

    for x in normalizados:
        producto = x["producto"]
        cantidad = x["cantidad"]

        inv, _ = Inventario.objects.get_or_create(
            id_producto=producto,
            defaults={
                "stock_actual": 0,
                "stock_minimo": 0,
                "stock_maximo": 0,
                "fecha_actualizacion": ahora,
            }
        )

        # Normaliza NULL -> 0
        Inventario.objects.filter(id_inventario=inv.id_inventario, stock_actual__isnull=True).update(stock_actual=0)

        Inventario.objects.filter(id_inventario=inv.id_inventario).update(
            stock_actual=F("stock_actual") + cantidad,
            fecha_actualizacion=ahora,
        )

        movimientos.append(MovimientoInventario(
            id_producto=producto,
            id_usuario=usuario,
            tipo_movimiento="COMPRA",
            cantidad=cantidad,
            referencia=f"COMPRA:{compra.id_compra}",
            fecha_movimiento=ahora,
            observaciones=f"Entrada por compra. Factura {numero_factura}. Proveedor {proveedor.nombre}. IVA {iva_rate}%.",
        ))

    MovimientoInventario.objects.bulk_create(movimientos)

    return JsonResponse({
        "ok": True,
        "id_compra": compra.id_compra,
        "numero_factura": numero_factura,
        "iva_rate": str(iva_rate),
        "subtotal": str(subtotal),
        "impuesto": str(impuesto),
        "total": str(total),
    })


# ============================================================
# NUEVO: APIs para el modal "Nuevo producto"
# ============================================================

@login_required_custom
@require_POST
@transaction.atomic
def api_proveedor_upsert(request):
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

    # Evitar duplicado por nombre dentro del mismo proveedor (recomendado)
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

    # Opción B: inventario siempre existe y siempre inicia en 0 al crear producto.
    # (El stock solo sube cuando se registra una compra.)
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


from django.views.decorators.http import require_GET

@login_required_custom
@require_GET
def api_proveedores_buscar(request):
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