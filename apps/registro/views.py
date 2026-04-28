from io import BytesIO

from openpyxl import Workbook
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.auth import login_required_custom
from apps.core.models import Categoria, Inventario, MovimientoInventario, Producto, Proveedor, Usuario

from .forms import MovementForm, ProductForm


def _stock_status(stock_actual, stock_minimo):
    stock_actual = stock_actual or 0
    stock_minimo = stock_minimo or 0
    if stock_actual <= 0:
        return "Agotado"
    if stock_actual <= stock_minimo:
        return "Bajo"
    return "Normal"


def _inventory_queryset(query_text="", category_id=""):
    queryset = Producto.objects.select_related("id_categoria", "id_proveedor").all()
    if query_text:
        queryset = queryset.filter(nombre__icontains=query_text)
    if category_id:
        queryset = queryset.filter(id_categoria_id=category_id)
    return queryset


def _build_rows(queryset):
    inventory_map = {
        row.id_producto_id: row
        for row in Inventario.objects.select_related("id_producto").all()
    }
    rows = []
    for product in queryset:
        inventory = inventory_map.get(product.id_producto)
        stock_actual = inventory.stock_actual if inventory and inventory.stock_actual is not None else 0
        stock_minimo = inventory.stock_minimo if inventory and inventory.stock_minimo is not None else 0
        rows.append(
            {
                "product": product,
                "inventory": inventory,
                "codigo": product.id_producto,
                "nombre": product.nombre,
                "categoria": product.id_categoria.nombre if product.id_categoria else "Sin categoría",
                "categoria_id": product.id_categoria_id,
                "proveedor": product.id_proveedor.nombre if product.id_proveedor else "",
                "proveedor_id": product.id_proveedor_id,
                "precio_compra": product.precio_compra or 0,
                "precio_venta": product.precio_venta or 0,
                "unidad_medida": product.unidad_medida or "",
                "descripcion": product.descripcion or "",
                "stock_actual": stock_actual,
                "stock_minimo": stock_minimo,
                "estado": _stock_status(stock_actual, stock_minimo),
            }
        )
    return rows


def _sort_rows(rows, sort_key):
    reverse = sort_key.startswith("-")
    key = sort_key.lstrip("-")
    mapping = {
        "codigo": lambda row: row["codigo"],
        "nombre": lambda row: row["nombre"].lower(),
        "categoria": lambda row: row["categoria"].lower(),
        "precio_venta": lambda row: row["precio_venta"],
        "stock_actual": lambda row: row["stock_actual"],
        "stock_minimo": lambda row: row["stock_minimo"],
        "estado": lambda row: row["estado"],
    }
    return sorted(rows, key=mapping.get(key, mapping["codigo"]), reverse=reverse)


def _build_product_form(product=None):
    categories = Categoria.objects.order_by("nombre")
    providers = Proveedor.objects.order_by("nombre")
    inventory = None
    if product:
        inventory = Inventario.objects.filter(id_producto=product).first()

    initial = {
        "product_id": product.id_producto if product else "",
        "codigo_producto": product.id_producto if product else "",
        "nombre": product.nombre if product else "",
        "descripcion": product.descripcion if product else "",
        "categoria": product.id_categoria_id if product else "",
        "proveedor": product.id_proveedor_id if product else "",
        "unidad_medida": product.unidad_medida if product else "unidad",
        "precio_compra": product.precio_compra if product and product.precio_compra is not None else "",
        "precio_venta": product.precio_venta if product and product.precio_venta is not None else "",
        "stock_actual": inventory.stock_actual if inventory and inventory.stock_actual is not None else 0,
        "stock_minimo": inventory.stock_minimo if inventory and inventory.stock_minimo is not None else 0,
    }
    return ProductForm(initial=initial, categories=categories, providers=providers)


def _current_user(request):
    user_id = request.session.get("id_usuario")
    if not user_id:
        return None
    return Usuario.objects.filter(id_usuario=user_id).first()


def _selected_product_from_request(request):
    selected_id = (request.GET.get("product") or request.GET.get("producto_id") or "").strip()
    if not selected_id:
        return None
    return Producto.objects.select_related("id_categoria", "id_proveedor").filter(id_producto=selected_id).first()


@login_required_custom
def index(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_product":
            return _save_product(request)
        if action == "delete_product":
            return _delete_product(request)
        if action == "save_movement":
            return _save_movement(request)

    query_text = (request.GET.get("q") or "").strip()
    category_id = (request.GET.get("category") or "").strip()
    sort_key = (request.GET.get("sort") or "codigo").strip()

    queryset = _inventory_queryset(query_text=query_text, category_id=category_id)
    rows = _sort_rows(_build_rows(queryset), sort_key)

    selected_product = _selected_product_from_request(request)
    if not selected_product and rows:
        selected_product = rows[0]["product"]

    selected_row = None
    if selected_product:
        for row in rows:
            if row["codigo"] == selected_product.id_producto:
                selected_row = row
                break

    product_form = _build_product_form(selected_product)
    movement_form = MovementForm()
    movement_history = MovementHistory(selected_product)

    context = {
        "categories": Categoria.objects.order_by("nombre"),
        "providers": Proveedor.objects.order_by("nombre"),
        "rows": rows,
        "selected_row": selected_row,
        "product_form": product_form,
        "movement_form": movement_form,
        "movement_history": movement_history,
        "query_text": query_text,
        "category_id": category_id,
        "sort_key": sort_key,
        "selected_product_id": selected_product.id_producto if selected_product else "",
        "selected_product_name": selected_product.nombre if selected_product else "",
        "product_options": list(_inventory_queryset().values("id_producto", "nombre")),
    }
    return render(request, "registro/index.html", context)


def MovementHistory(selected_product):
    queryset = MovimientoInventario.objects.select_related("id_producto", "id_usuario").order_by("-fecha_movimiento")
    if selected_product:
        queryset = queryset.filter(id_producto=selected_product)
    return queryset[:20]


def _save_product(request):
    categories = Categoria.objects.order_by("nombre")
    providers = Proveedor.objects.order_by("nombre")
    form = ProductForm(request.POST, categories=categories, providers=providers)
    if not form.is_valid():
        messages.error(request, "Revisa los campos del producto antes de guardar.")
        return _render_with_form(request, product_form=form)

    data = form.cleaned_data
    try:
        with transaction.atomic():
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
            if not product.fecha_creacion:
                product.fecha_creacion = timezone.now()
            product.save()

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
        messages.success(request, "Producto eliminado correctamente.")
    except Producto.DoesNotExist:
        messages.error(request, "El producto ya no existe.")
    except IntegrityError:
        messages.error(request, "No se pudo eliminar porque el producto ya tiene referencias en otras tablas.")
    return redirect(request.path)


def _save_movement(request):
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
                raise ValueError("El stock no puede quedar en negativo.")
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
        messages.success(request, "Movimiento registrado correctamente.")
        return redirect(f"{request.path}?product={product.id_producto}")
    except ValueError as exc:
        messages.error(request, str(exc))
    except IntegrityError as exc:
        messages.error(request, f"No se pudo registrar el movimiento: {exc}")
    return _render_with_form(request, movement_form=form)


def _resolve_product_from_label(label):
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
    query_text = (request.GET.get("q") or "").strip()
    category_id = (request.GET.get("category") or "").strip()
    sort_key = (request.GET.get("sort") or "codigo").strip()
    queryset = _inventory_queryset(query_text=query_text, category_id=category_id)
    rows = _sort_rows(_build_rows(queryset), sort_key)
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
        "categories": Categoria.objects.order_by("nombre"),
        "providers": Proveedor.objects.order_by("nombre"),
        "rows": rows,
        "selected_row": selected_row,
        "product_form": product_form,
        "movement_form": movement_form,
        "movement_history": MovementHistory(selected_product),
        "query_text": query_text,
        "category_id": category_id,
        "sort_key": sort_key,
        "selected_product_id": selected_product.id_producto if selected_product else "",
        "selected_product_name": selected_product.nombre if selected_product else "",
        "product_options": list(_inventory_queryset().values("id_producto", "nombre")),
    }
    return render(request, "registro/index.html", context)


@login_required_custom
def export_excel(request):
    query_text = (request.GET.get("q") or "").strip()
    category_id = (request.GET.get("category") or "").strip()
    rows = _sort_rows(_build_rows(_inventory_queryset(query_text=query_text, category_id=category_id)), "codigo")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Inventario"
    sheet.append(["Código", "Nombre", "Categoría", "Precio venta", "Stock actual", "Stock mínimo", "Estado"])
    for row in rows:
        sheet.append([
            row["codigo"],
            row["nombre"],
            row["categoria"],
            float(row["precio_venta"]),
            row["stock_actual"],
            row["stock_minimo"],
            row["estado"],
        ])

    movements = workbook.create_sheet("Movimientos")
    movements.append(["Fecha", "Producto", "Tipo", "Cantidad", "Usuario", "Observación"])
    for movement in MovimientoInventario.objects.select_related("id_producto", "id_usuario").order_by("-fecha_movimiento")[:200]:
        movements.append([
            movement.fecha_movimiento,
            movement.id_producto.nombre if movement.id_producto else "",
            movement.tipo_movimiento,
            movement.cantidad,
            movement.id_usuario.nombre if movement.id_usuario else "Sistema",
            movement.observaciones or "",
        ])

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="inventario_ferreteria.xlsx"'
    return response