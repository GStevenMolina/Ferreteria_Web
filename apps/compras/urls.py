"""
urls.py (módulo Compras)

Define las rutas del módulo Compras.

Incluye:
- Página principal del módulo
- API para registrar compras
- APIs para listar/buscar proveedores y productos
- APIs para el modal de creación (upsert proveedor/categoría y crear producto)
"""

from django.urls import path
from . import views

app_name = "compras"

urlpatterns = [
    # Página principal
    path("", views.index, name="index"),
    path("proveedor/", views.proveedor, name="proveedor"),

    # Registrar compra (POST)
    path("nueva/", views.nueva_compra, name="nueva_compra"),

    # APIs: carga principal
    path("api/proveedores/", views.api_proveedores, name="api_proveedores"),
    path("api/productos/", views.api_productos, name="api_productos"),

    # API: autocomplete de proveedores
    path("api/proveedores/buscar/", views.api_proveedores_buscar, name="api_proveedores_buscar"),
    path("api/categorias/buscar/", views.api_categorias_buscar, name="api_categorias_buscar"),

    # APIs: Modal nuevo producto
    # Upsert = si existe lo reutiliza/actualiza, si no existe lo crea
    path("api/proveedor/upsert/", views.api_proveedor_upsert, name="api_proveedor_upsert"),
    path("api/proveedor/actualizar/", views.api_proveedor_actualizar, name="api_proveedor_actualizar"),
    path("api/categoria/upsert/", views.api_categoria_upsert, name="api_categoria_upsert"),
    path("api/producto/crear/", views.api_producto_crear, name="api_producto_crear"),

    # Generar Factura .pdf
    path('factura/<int:factura_id>/pdf/', views.generar_factura_pdf, name='generar_factura_pdf'),
]