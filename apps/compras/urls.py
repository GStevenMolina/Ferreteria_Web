from django.urls import path
from . import views

app_name = "compras"

urlpatterns = [
    path("", views.index, name="index"),

    path("nueva/", views.nueva_compra, name="nueva_compra"),
    path("api/proveedores/", views.api_proveedores, name="api_proveedores"),
    path("api/productos/", views.api_productos, name="api_productos"),
    path("api/proveedores/buscar/", views.api_proveedores_buscar, name="api_proveedores_buscar"),

    # Modal nuevo producto
    path("api/proveedor/upsert/", views.api_proveedor_upsert, name="api_proveedor_upsert"),
    path("api/categoria/upsert/", views.api_categoria_upsert, name="api_categoria_upsert"),
    path("api/producto/crear/", views.api_producto_crear, name="api_producto_crear"),
]