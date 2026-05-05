from __future__ import annotations

from collections import Counter

from django.db.models import Count, Sum

from apps.core.models import Categoria, Inventario, MovimientoInventario, Producto, Proveedor


def stock_status(stock_actual, stock_minimo):
    stock_actual = stock_actual or 0
    stock_minimo = stock_minimo or 0
    if stock_actual <= 0:
        return "Agotado"
    if stock_actual <= stock_minimo:
        return "Bajo"
    return "Normal"


def inventory_queryset(query_text: str = "", category_id: str = ""):
    queryset = Producto.objects.select_related("id_categoria", "id_proveedor").all()
    if query_text:
        queryset = queryset.filter(nombre__icontains=query_text)
    if category_id:
        queryset = queryset.filter(id_categoria_id=category_id)
    return queryset


def build_rows(queryset):
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
                "estado": stock_status(stock_actual, stock_minimo),
            }
        )
    return rows


def sort_rows(rows, sort_key):
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


def build_product_form_initial(product=None):
    inventory = None
    if product:
        inventory = Inventario.objects.filter(id_producto=product).first()

    return {
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


def movement_history(selected_product=None, limit=20):
    queryset = MovimientoInventario.objects.select_related("id_producto", "id_usuario").order_by("-fecha_movimiento")
    if selected_product:
        queryset = queryset.filter(id_producto=selected_product)
    return queryset[:limit]


def report_summary(queryset=None):
    queryset = queryset or Producto.objects.all()
    rows = build_rows(queryset)
    totals = Counter(row["estado"] for row in rows)
    low_stock = sum(1 for row in rows if row["estado"] == "Bajo") + sum(1 for row in rows if row["estado"] == "Agotado")
    return {
        "total_productos": len(rows),
        "productos_bajo_stock": low_stock,
        "productos_normales": totals.get("Normal", 0),
        "productos_bajos": totals.get("Bajo", 0),
        "productos_agotados": totals.get("Agotado", 0),
    }


def report_kpis(product_id: str = "", movement_type: str = "", start_date=None, end_date=None):
    movements = MovimientoInventario.objects.select_related("id_producto", "id_usuario").order_by("-fecha_movimiento")
    if product_id:
        movements = movements.filter(id_producto_id=product_id)
    if movement_type:
        movements = movements.filter(tipo_movimiento=movement_type)
    if start_date:
        movements = movements.filter(fecha_movimiento__date__gte=start_date)
    if end_date:
        movements = movements.filter(fecha_movimiento__date__lte=end_date)

    entrada_total = movements.filter(tipo_movimiento__in=["entrada", "ajuste_entrada"]).aggregate(total=Sum("cantidad"))["total"] or 0
    salida_total = movements.filter(tipo_movimiento__in=["salida", "ajuste_salida"]).aggregate(total=Sum("cantidad"))["total"] or 0
    return {
        "movements": movements,
        "total_entradas": entrada_total,
        "total_salidas": salida_total,
        "conteo_movimientos": movements.count(),
    }


def categories_and_providers():
    return {
        "categories": Categoria.objects.order_by("nombre"),
        "providers": Proveedor.objects.order_by("nombre"),
    }