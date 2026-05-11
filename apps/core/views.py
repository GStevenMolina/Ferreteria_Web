from datetime import timedelta

from django.db.models import CharField, Count, DecimalField, F, IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.auth import login_required_custom
from apps.core.models import Categoria, Compra, Devolucion, Inventario, MovimientoInventario, Producto, Venta


def _money_total(queryset, field_name):
    """Agrega un total decimal sin introducir lógica adicional en el template."""
    return queryset.aggregate(
        total=Coalesce(
            Sum(field_name),
            Value(0),
            output_field=DecimalField(max_digits=18, decimal_places=2),
        )
    )["total"] or 0


def _daily_series(queryset, date_field, amount_field, start_date, days):
    """Construye una serie diaria rellenando los días sin datos con cero."""
    grouped = (
        queryset.filter(**{f"{date_field}__date__gte": start_date})
        .annotate(day=TruncDate(date_field))
        .values("day")
        .annotate(
            total=Coalesce(
                Sum(amount_field),
                Value(0),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            )
        )
        .order_by("day")
    )
    totals = {row["day"]: float(row["total"] or 0) for row in grouped}
    labels = [day.strftime("%d/%m") for day in days]
    values = [totals.get(day, 0.0) for day in days]
    return labels, values


@login_required_custom
def dashboard_view(request):
    """Dashboard operativo reutilizando datos ya existentes del sistema."""
    today = timezone.localdate()
    now = timezone.now()
    seven_days_ago = today - timedelta(days=6)
    recent_cutoff = now - timedelta(days=7)

    products_qs = Producto.objects.select_related("id_categoria", "id_proveedor")
    inventory_qs = Inventario.objects.select_related("id_producto", "id_producto__id_categoria")

    stock_zero_qs = inventory_qs.filter(Q(stock_actual__isnull=True) | Q(stock_actual__lte=0))
    stock_low_qs = inventory_qs.filter(stock_minimo__gt=0, stock_actual__gt=0, stock_actual__lt=F("stock_minimo"))
    stock_min_qs = inventory_qs.filter(stock_minimo__gt=0, stock_actual=F("stock_minimo"))

    top_products_rows = list(
        Producto.objects.values("id_producto")
        .annotate(
            sold_units=Coalesce(
                Sum("detalleventa__cantidad"),
                Value(0),
                output_field=IntegerField(),
            )
        )
        .filter(sold_units__gt=0)
        .order_by("-sold_units", "id_producto")[:10]
    )
    top_product_names = dict(
        Producto.objects.filter(id_producto__in=[row["id_producto"] for row in top_products_rows]).values_list(
            "id_producto",
            "nombre",
        )
    )

    category_rows = list(
        Producto.objects.values("id_categoria_id")
        .annotate(total=Count("id_producto"))
        .order_by("-total", "id_categoria_id")
    )
    category_names = {
        category.id_categoria: category.nombre
        for category in Categoria.objects.filter(
            id_categoria__in=[row["id_categoria_id"] for row in category_rows if row["id_categoria_id"]]
        )
    }

    day_range = [seven_days_ago + timedelta(days=index) for index in range(7)]
    purchase_labels, purchase_values = _daily_series(Compra.objects.all(), "fecha", "total", seven_days_ago, day_range)
    sale_labels, sale_values = _daily_series(Venta.objects.all(), "fecha", "total", seven_days_ago, day_range)

    context = {
        "total_productos": products_qs.count(),
        "productos_stock_bajo": stock_low_qs.count(),
        "productos_agotados": stock_zero_qs.count(),
        "ventas_del_dia": _money_total(Venta.objects.filter(fecha__date=today), "total"),
        "compras_del_dia": _money_total(Compra.objects.filter(fecha__date=today), "total"),
        "movimientos_recientes": MovimientoInventario.objects.filter(fecha_movimiento__gte=recent_cutoff).count(),
        "top_products_labels": [top_product_names.get(row["id_producto"], f"Producto {row['id_producto']}") for row in top_products_rows],
        "top_products_values": [int(row["sold_units"] or 0) for row in top_products_rows],
        "flow_labels": purchase_labels,
        "flow_purchase_values": purchase_values,
        "flow_sale_values": sale_values,
        "category_labels": [category_names.get(row["id_categoria_id"], "Sin categoría") for row in category_rows],
        "category_values": [int(row["total"] or 0) for row in category_rows],
        "alert_zero_stock": stock_zero_qs.order_by("id_producto_id")[:5],
        "alert_low_stock": stock_low_qs.order_by("id_producto_id")[:5],
        "alert_min_stock": stock_min_qs.order_by("id_producto_id")[:5],
        "recent_purchases": Compra.objects.select_related("id_proveedor", "id_usuario").order_by("-fecha")[:5],
        "recent_sales": Venta.objects.select_related("id_cliente", "id_usuario").order_by("-fecha")[:5],
        "recent_returns": Devolucion.objects.select_related("id_producto", "id_venta").order_by("-fecha")[:5],
    }
    return render(request, "dashboard.html", context)