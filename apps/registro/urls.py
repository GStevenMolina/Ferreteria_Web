from django.urls import path
from . import views

app_name = "registro"

urlpatterns = [
    path("", views.index, name="index"),
    path("reportes/", views.reportes, name="reportes"),
    path("exportar/", views.export_excel, name="export_excel"),
]