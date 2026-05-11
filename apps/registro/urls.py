from django.urls import path
from . import views

app_name = "registro"

urlpatterns = [
    path("", views.index, name="index"),
    path("reportes/", views.reportes, name="reportes"),
    path("api/autocomplete/", views.autocomplete_products, name="autocomplete_products"),
    path("api/quick_update/", views.quick_update_product, name="quick_update_product"),
    path("exportar/", views.export_excel, name="export_excel"),
]