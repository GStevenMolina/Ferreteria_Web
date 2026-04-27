from django.urls import path
from . import views

app_name = "registro"

urlpatterns = [
    path("", views.index, name="index"),
    path("exportar/", views.export_excel, name="export_excel"),
]