from django.urls import path
from . import views

app_name = "ventas"

urlpatterns = [
    path("", views.index, name="index"),
    path('guardar/', views.guardar_venta, name='guardar_venta'),
    path('buscar-cliente/', views.buscar_cliente, name='buscar_cliente'),
    path('crear-cliente/', views.crear_cliente, name='crear_cliente'),
]
