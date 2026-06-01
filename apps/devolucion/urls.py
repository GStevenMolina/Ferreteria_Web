# apps/devolucion/urls.py

from django.urls import path
from . import views

app_name = "devolucion"

urlpatterns = [
    # Página principal
    path("", views.index, name="index"),

    # Endpoint AJAX para cargar productos según factura
    path(
        "obtener-productos/<int:id_factura>/",
        views.obtener_productos,
        name="obtener_productos"
    ),
    path(
    'reporte/pdf/',
    views.reporte_devoluciones_pdf,
    name='reporte_pdf'
),

]