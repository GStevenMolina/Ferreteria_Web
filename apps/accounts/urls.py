from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    path("password/forgot/", views.forgot_password_code, name="password_forgot"),
    path("password/reset/", views.password_reset_code_verify, name="password_reset_code_verify"),
    
    path("usuarios/", views.users_list_view, name="users_list"),
    path("usuarios/nuevo/", views.create_user_view, name="create_user"),
    path("usuarios/<int:id_usuario>/toggle-activo/", views.toggle_user_active_view, name="toggle_user_active"),
]