from __future__ import annotations
from collections import Counter
# SE AGREGÓ "F" AL IMPORT PARA QUE FUNCIONEN LOS FILTROS DE ESTADO COMPARATIVOS
from django.db.models import Count, Sum, F
from apps.core.models import Categoria, Inventario, MovimientoInventario, Producto, Proveedor
import json


# =========================================================================
# 🔍 CONSULTAS GENERALES Y FILTROS AVANZADOS DEL INVENTARIO
# =========================================================================

def inventory_queryset(query_text: str = "", category_id: str = "", stock_range: str = "", provider_id: str = "", status_filter: str = ""):
    """
    Devuelve un queryset de productos filtrado por texto de búsqueda, categoría,
    rango de stock, proveedor y estado físico/lógico de disponibilidad.
    """
    # Iniciamos la consulta base
    queryset = Producto.objects.select_related("id_categoria", "id_proveedor").all()
    
    # Filtro de Estado Lógico (Nuevo atributo 'estado') y Estado Físico del Stock
    if status_filter:
        if status_filter == "Agotado":
            queryset = queryset.filter(estado=True, inventario__stock_actual__lte=0)
        elif status_filter == "Bajo":
            queryset = queryset.filter(
                estado=True,
                inventario__stock_actual__gt=0,
                inventario__stock_actual__lte=F('inventario__stock_minimo')
            )
        elif status_filter == "Normal":
            queryset = queryset.filter(
                estado=True,
                inventario__stock_actual__gt=F('inventario__stock_minimo')
            )
        elif status_filter == "Inactivo":
            queryset = queryset.filter(estado=False)
    else:
        # SI NO HAY FILTRO SELECCIONADO: Por defecto ocultamos los productos deshabilitados/inactivos
        queryset = queryset.filter(estado=True)
    
    # Filtro 1: Texto
    if query_text:
        queryset = queryset.filter(nombre__icontains=query_text)
        
    # Filtro 2: Categoría
    if category_id:
        queryset = queryset.filter(id_categoria_id=category_id)
        
    # Filtro 3: Proveedor
    if provider_id:
        queryset = queryset.filter(id_proveedor_id=provider_id)

    # Filtro 4: Rango de Stock
    if stock_range:
        if stock_range == "10-20":
            queryset = queryset.filter(inventario__stock_actual__gte=10, inventario__stock_actual__lte=20)
        elif stock_range == "20-40":
            queryset = queryset.filter(inventario__stock_actual__gte=20, inventario__stock_actual__lte=40)
        elif stock_range == "40-60":
            queryset = queryset.filter(inventario__stock_actual__gte=20, inventario__stock_actual__lte=60)
        elif stock_range == "60+":
            queryset = queryset.filter(inventario__stock_actual__gt=60)

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
        
        estado_texto = "Inactivo" if not product.estado else stock_status(stock_actual, stock_minimo)

        # 🔥 CONSTRUIMOS EL JSON COMPLETO QUE LEERÁ TU MODAL EN JS
        product_json = json.dumps({
            'id_producto': product.id_producto,
            'codigo': product.id_producto,
            'nombre': product.nombre,
            'precio_compra': float(product.precio_compra) if product.precio_compra else 0.0,
            'precio_venta': float(product.precio_venta) if product.precio_venta else 0.0,
            'stock_actual': int(stock_actual),
            'stock_minimo': int(stock_minimo),
            'unidad_medida': product.unidad_medida or "Unidad",
            'estado': "Activo" if product.estado else "Inactivo",
            'id_categoria': product.id_categoria_id if product.id_categoria_id else "",
            'id_proveedor': product.id_proveedor_id if product.id_proveedor_id else ""
        }, ensure_ascii=False)

        rows.append(
            {
                "product": product,
                "inventory": inventory,
                "codigo": product.id_producto,
                "nombre": product.nombre,
                "categoria": product.id_categoria.nombre if product.id_categoria else "Sin categoría",
                "categoria_id": product.id_categoria_id,
                "proveedor": product.id_proveedor.nombre if product.id_proveedor else "Sin Proveedor",
                "proveedor_id": product.id_proveedor_id,
                "precio_compra": product.precio_compra or 0,
                "precio_venta": product.precio_venta or 0,
                "unidad_medida": product.unidad_medida or "",
                "descripcion": product.descripcion or "",
                "stock_actual": stock_actual,
                "stock_minimo": stock_minimo,
                "estado": estado_texto,
                "product_json": product_json,  # 🔥 SE PASA LIMPIO AL ATRIBUTO data-product DEL TR
            }
        )
    return rows

# =========================================================================
# ⚙️ LÓGICA DE CONTROL Y AUXILIARES
# =========================================================================

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


def build_product_form_initial(product=None):
    """
    Construye el diccionario de valores iniciales para pre-poblar el
    formulario de producto con los datos del objeto Producto e Inventario asociado.
    """
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


# =========================================================================
# 📊 HISTORIAL, KPIS Y RESÚMENES DE REPORTES
# =========================================================================

def movement_history(selected_product=None, limit=20):
    """Devuelve los últimos movimientos de inventario."""
    queryset = MovimientoInventario.objects.select_related("id_producto", "id_usuario").order_by("-fecha_movimiento")
    if selected_product:
        queryset = queryset.filter(id_producto=selected_product)
    return queryset[:limit]


def report_summary(queryset=None):
    """Calcula un resumen estadístico numérico del inventario actual."""
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


def report_kpis(product_id: str = "", movement_type: str = "", start_date=None, end_date=None, query_text: str = "", category_id: str = ""):
    """Calcula los KPIs cuantitativos de flujos y movimientos históricos."""
    movements = MovimientoInventario.objects.select_related("id_producto", "id_usuario").order_by("-fecha_movimiento")
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

    entrada_total = movements.filter(tipo_movimiento__in=["entrada", "ajuste_entrada"]).aggregate(total=Sum("cantidad"))["total"] or 0
    salida_total = movements.filter(tipo_movimiento__in=["salida", "ajuste_salida"]).aggregate(total=Sum("cantidad"))["total"] or 0
    return {
        "movements": movements,
        "total_entradas": entrada_total,
        "total_salidas": salida_total,
        "conteo_movimientos": movements.count(),
    }


def categories_and_providers():
    """Devuelve las categorías y proveedores disponibles, ordenados por nombre."""
    return {
        "categories": Categoria.objects.order_by("nombre"),
        "providers": Proveedor.objects.order_by("nombre"),
    }