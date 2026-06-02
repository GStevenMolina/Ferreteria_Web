from django.urls import path
from . import views

app_name = 'cliente'

urlpatterns = [
    path('', views.index, name='index'),

    path(
        "editar/<int:id>/",
        views.editar_cliente,
        name="editar"
    ),

    path(
        "eliminar/<int:id>/",
        views.eliminar_cliente,
        name="eliminar"
    ),

    # NUEVA RUTA AGREGADA
    path(
        "cambiar-estado/<int:id>/",
        views.cambiar_estado_cliente,
        name="cambiar_estado"
    ),
]