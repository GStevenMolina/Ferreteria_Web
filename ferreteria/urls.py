"""
URL configuration for ferreteria project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.shortcuts import render
from django.urls import path, include
from django.contrib.auth.decorators import login_required

@login_required

def dashboard(request):
    return render(request, "dashboard.html")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", dashboard, name="dashboard"),
    path("accounts/", include("apps.accounts.urls")),
    
    path("compras/", include("apps.compras.urls")),
    path("ventas/", include("apps.ventas.urls")),
    path("registro/", include("apps.registro.urls")),
    path("devolucion/", include("apps.devolucion.urls")),

]