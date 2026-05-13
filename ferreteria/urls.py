from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

from apps.accounts.auth import login_required_custom
from apps.core.views import dashboard_view


def home(request):
    # Si hay sesión, entra al dashboard
    if request.session.get("id_usuario"):
        return redirect("/dashboard/")

    # Si no hay sesión, manda al login (ruta real en tu proyecto)
    return redirect("/login/")


urlpatterns = [
    path("admin/", admin.site.urls),

    # Root router + dashboard
    path("", home, name="home"),
    path("dashboard/", dashboard_view, name="dashboard"),

    # Accounts en raíz (porque tu login está en /login/)
    path("", include("apps.accounts.urls")),

    # Apps
    path("compras/", include("apps.compras.urls")),
    path("ventas/", include("apps.ventas.urls")),
    path("registro/", include("apps.registro.urls")),
    path("devolucion/", include("apps.devolucion.urls")),
    path('cliente/', include('apps.cliente.urls')),
    
]