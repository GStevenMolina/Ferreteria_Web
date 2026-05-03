"""Rutas de la aplicación accounts.

Define endpoints para login/logout, gestión de usuarios y el flujo de recuperación local
utilizado en pruebas (password/forgot-local/ y password/reset-local/<token>/).
"""

from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("password/forgot-local/", views.forgot_password_local_view, name="password_forgot_local"),
    path("password/reset-local/<str:token>/", views.password_reset_local_view, name="password_reset_local"),

    # (6) Cambiar contraseña
    path("password/", views.change_password_view, name="change_password"),

    # (7) Crear usuario (panel)
    path("usuarios/nuevo/", views.create_user_view, name="create_user"),
    
    path("usuarios/", views.users_list_view, name="users_list"),
    path("usuarios/<int:id_usuario>/toggle-activo/", views.toggle_user_active_view, name="toggle_user_active"),
]