from io import BytesIO

from openpyxl import Workbook
from django.contrib import messages
from django.db import IntegrityError, transaction
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


def _build_product_form(product=None):
    data = categories_and_providers()
    return ProductForm(initial=build_product_form_initial(product), categories=data["categories"], providers=data["providers"])


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


def _parse_optional_date(request, key):
    raw = (request.GET.get(key) or "").strip()
    if not raw:
        return None
    return parse_date(raw)


def _excel_safe_datetime(value):
    if not value:
        return ""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
        return value.replace(tzinfo=None)
    return value


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

    product_form = _build_product_form(selected_product)
    movement_form = MovementForm()

    categories = categories_and_providers()["categories"]
    product_options = list(inventory_queryset().values("id_producto", "nombre"))

    context = {
        "categories": categories,
        "rows": rows,
        "selected_row": selected_row,
        "product_form": product_form,
        "movement_form": movement_form,
        "query_text": query_text,
        "category_id": category_id,
        "sort_key": sort_key,
        "selected_product_id": selected_product.id_producto if selected_product else "",
        "selected_product_name": selected_product.nombre if selected_product else "",
        "product_options": product_options,
    }
    return render(request, "registro/index.html", context)


def _save_product(request):
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
def export_excel(request):
    query_text = (request.GET.get("q") or "").strip()
    category_id = (request.GET.get("category") or "").strip()
    product_id = (request.GET.get("product") or "").strip()
    movement_type = (request.GET.get("movement_type") or "").strip()
    start_date = _parse_optional_date(request, "from")
    end_date = _parse_optional_date(request, "to")
    rows = sort_rows(build_rows(inventory_queryset(query_text=query_text, category_id=category_id)), "codigo")
    movements = report_kpis(
        product_id=product_id,
        movement_type=movement_type,
        start_date=start_date,
        end_date=end_date,
    )["movements"]

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

    movements_sheet = workbook.create_sheet("Movimientos")
    movements_sheet.append(["Fecha", "Producto", "Tipo", "Cantidad", "Usuario", "Observación"])
    for movement in movements[:200]:
        movements_sheet.append([
            _excel_safe_datetime(movement.fecha_movimiento),
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


@login_required_custom
def reportes(request):
    query_text = (request.GET.get("q") or "").strip()
    category_id = (request.GET.get("category") or "").strip()
    product_id = (request.GET.get("product") or "").strip()
    movement_type = (request.GET.get("movement_type") or "").strip()
    start_date = _parse_optional_date(request, "from")
    end_date = _parse_optional_date(request, "to")

    rows = sort_rows(build_rows(inventory_queryset(query_text=query_text, category_id=category_id)), "codigo")
    summary = report_summary(inventory_queryset(query_text=query_text, category_id=category_id))
    kpis = report_kpis(product_id=product_id, movement_type=movement_type, start_date=start_date, end_date=end_date)

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