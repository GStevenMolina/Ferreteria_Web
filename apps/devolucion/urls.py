from django.urls import path
from . import views

app_name = "devolucion"

urlpatterns = [
    path("", views.index, name="index"),
]