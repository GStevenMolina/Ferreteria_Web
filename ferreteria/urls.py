from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render

from apps.accounts.auth import login_required_custom

@login_required_custom
def dashboard(request):
    return render(request, "dashboard.html")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", dashboard, name="dashboard"),
    path("", include("apps.accounts.urls")),

    path("compras/", include("apps.compras.urls")),
    path("ventas/", include("apps.ventas.urls")),
    path("registro/", include("apps.registro.urls")),
    path("devolucion/", include("apps.devolucion.urls")),
]