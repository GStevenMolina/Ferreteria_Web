from __future__ import annotations

from collections import Counter

from django.db.models import Count, Sum

from apps.core.models import Categoria, Inventario, MovimientoInventario, Producto, Proveedor


# Lógica de estado del stock

def stock_status(stock_actual, stock_minimo):
    """
    Determina el estado de stock de un producto:
      - 'Agotado': stock en cero o negativo.
      - 'Bajo': stock igual o inferior al mínimo definido.
      - 'Normal': stock por encima del mínimo.
    """
    stock_actual = stock_actual or 0
    stock_minimo = stock_minimo or 0
    if stock_actual <= 0:
        return "Agotado"
    if stock_actual <= stock_minimo:
        return "Bajo"
    return "Normal"


# Consultas de inventario

def inventory_queryset(query_text: str = "", category_id: str = ""):
    """
    Devuelve un queryset de productos filtrado por texto de búsqueda (nombre)
    y/o por categoría. Incluye relaciones con categoría y proveedor para
    evitar consultas adicionales al construir las filas.
    """
    queryset = Producto.objects.select_related("id_categoria", "id_proveedor").all()
    if query_text:
        queryset = queryset.filter(nombre__icontains=query_text)
    if category_id:
        queryset = queryset.filter(id_categoria_id=category_id)
    return queryset


def build_rows(queryset):
    """
    Construye una lista de diccionarios con todos los datos necesarios para
    renderizar cada fila de la tabla de inventario (producto + stock).
    Carga todos los registros de inventario en un mapa para minimizar las
    consultas a la base de datos.
    """
    # Mapear id_producto → registro de Inventario para acceso O(1)
    inventory_map = {
        row.id_producto_id: row
        for row in Inventario.objects.select_related("id_producto").all()
    }
    rows = []
    for product in queryset:
        inventory = inventory_map.get(product.id_producto)
        # Usar 0 como valor predeterminado si el registro de inventario no existe
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
    """
    Ordena la lista de filas por la clave indicada.
    Un guion ('-') al inicio del sort_key invierte el orden (descendente).
    Las claves no reconocidas caen al ordenamiento por 'codigo'.
    """
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


# Datos iniciales para el formulario de producto

def build_product_form_initial(product=None):
    """
    Construye el diccionario de valores iniciales para pre-poblar el
    formulario de producto con los datos del objeto Producto e Inventario
    asociado. Si no se pasa producto, devuelve valores vacíos/cero.
    """
    inventory = None
    if product:
        # Obtener el registro de inventario del producto, si existe
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


# Historial de movimientos

def movement_history(selected_product=None, limit=20):
    """
    Devuelve los últimos movimientos de inventario, opcionalmente filtrados
    por producto. El resultado se limita a 'limit' registros.
    """
    queryset = MovimientoInventario.objects.select_related("id_producto", "id_usuario").order_by("-fecha_movimiento")
    if selected_product:
        queryset = queryset.filter(id_producto=selected_product)
    return queryset[:limit]


# Resumen y KPIs para reportes

def report_summary(queryset=None):
    """
    Calcula un resumen estadístico del inventario:
      - total_productos: total de productos.
      - productos_bajo_stock: suma de productos bajos y agotados.
      - productos_normales / productos_bajos / productos_agotados: conteo por estado.
    """
    queryset = queryset or Producto.objects.all()
    rows = build_rows(queryset)
    totals = Counter(row["estado"] for row in rows)
    # Combinar 'Bajo' y 'Agotado' como productos con problema de stock
    low_stock = sum(1 for row in rows if row["estado"] == "Bajo") + sum(1 for row in rows if row["estado"] == "Agotado")
    return {
        "total_productos": len(rows),
        "productos_bajo_stock": low_stock,
        "productos_normales": totals.get("Normal", 0),
        "productos_bajos": totals.get("Bajo", 0),
        "productos_agotados": totals.get("Agotado", 0),
    }


def report_kpis(product_id: str = "", movement_type: str = "", start_date=None, end_date=None, query_text: str = "", category_id: str = ""):
    """
    Calcula los KPIs de movimientos de inventario con filtros opcionales:
      - product_id: filtrar por producto específico.
      - movement_type: filtrar por tipo de movimiento (entrada, salida, etc.).
      - start_date / end_date: filtrar por rango de fechas.
    Retorna los movimientos filtrados y los totales de entradas, salidas y conteo.
    """
    movements = MovimientoInventario.objects.select_related("id_producto", "id_usuario").order_by("-fecha_movimiento")
    # Filtrar por texto (nombre de producto) y/o categoría si se proporciona
    if query_text:
        movements = movements.filter(id_producto__nombre__icontains=query_text)
    if category_id:
        movements = movements.filter(id_producto__id_categoria_id=category_id)
    if product_id:
        movements = movements.filter(id_producto_id=product_id)
    if movement_type:
        movements = movements.filter(tipo_movimiento=movement_type)
    if start_date:
        movements = movements.filter(fecha_movimiento__date__gte=start_date)
    if end_date:
        movements = movements.filter(fecha_movimiento__date__lte=end_date)

    # Sumar cantidades de entradas y ajustes positivos
    entrada_total = movements.filter(tipo_movimiento__in=["entrada", "ajuste_entrada"]).aggregate(total=Sum("cantidad"))["total"] or 0
    # Sumar cantidades de salidas y ajustes negativos
    salida_total = movements.filter(tipo_movimiento__in=["salida", "ajuste_salida"]).aggregate(total=Sum("cantidad"))["total"] or 0
    return {
        "movements": movements,
        "total_entradas": entrada_total,
        "total_salidas": salida_total,
        "conteo_movimientos": movements.count(),
    }


# Catálogos auxiliares

def categories_and_providers():
    """Devuelve las categorías y proveedores disponibles, ordenados por nombre."""
    return {
        "categories": Categoria.objects.order_by("nombre"),
        "providers": Proveedor.objects.order_by("nombre"),
    }