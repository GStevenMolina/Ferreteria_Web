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

]