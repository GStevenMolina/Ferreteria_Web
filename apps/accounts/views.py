"""
Módulo de vistas de la app `accounts`.

Contiene las vistas relacionadas con autenticación y gestión de usuarios:
- login_view: autentica usuarios con protección anti fuerza-bruta y manejo de sesión.
- logout_view: cierra la sesión.
- change_password_view: cambio de contraseña para usuarios autenticados.
- create_user_view, users_list_view, toggle_user_active_view: funcionalidades de administración.
- forgot_password_local_view, password_reset_local_view: flujo de recuperación "local" para pruebas
    (genera token temporal guardado en cache y permite restablecer contraseña sin enviar emails).

Cada función intenta ser conservadora con la información mostrada para no filtrar si un email
existe en producción; el flujo local está pensado solo para entornos de pruebas.
"""

from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.http import HttpResponseForbidden
from django.urls import reverse
import time
import secrets

from apps.core.models import Usuario
from apps.accounts.auth import login_required_custom


MAX_LOGIN_ATTEMPTS = 5
LOGIN_BLOCK_SECONDS = 5 * 60  # 5 minutos
REMEMBER_ME_SECONDS = 60 * 60 * 24 * 7  # 7 días
RESET_PASSWORD_TOKEN_SECONDS = 15 * 60  # 15 minutos


@require_http_methods(["GET", "POST"])
def login_view(request):
    # Si ya está logueado, al dashboard
    if request.method == "GET":
        if request.session.get("id_usuario"):
            return redirect("/")
        return render(request, "accounts/login.html")

    email = (request.POST.get("email") or "").strip()
    password = request.POST.get("password") or ""
    remember_me = request.POST.get("remember_me") == "1"

    if not email or not password:
        messages.error(request, "Email y contraseña son requeridos.")
        return render(request, "accounts/login.html", {"email": email})

    # --- (4) Anti fuerza-bruta: bloqueo por IP + email ---
    ip = request.META.get("REMOTE_ADDR", "unknown")
    base_key = f"login_attempts:{ip}:{email.lower()}"
    blocked_until_key = f"{base_key}:blocked_until"

    now = int(time.time())
    blocked_until = cache.get(blocked_until_key)

    if blocked_until and now < blocked_until:
        remaining = blocked_until - now
        minutes = max(1, remaining // 60)
        messages.error(request, f"Demasiados intentos. Intenta de nuevo en ~{minutes} minuto(s).")
        return render(request, "accounts/login.html", {"email": email})

    usuario = Usuario.objects.filter(email=email).first()

    if usuario and not bool(usuario.activo):
        _register_failed_attempt(base_key, blocked_until_key, now)
        messages.error(request, "Tu usuario está inactivo. Contacta al administrador.")
        return render(request, "accounts/login.html", {"email": email})

    # Evitar dar pistas: mismo mensaje si usuario no existe o password no coincide
    if not usuario or not usuario.password:
        _register_failed_attempt(base_key, blocked_until_key, now)
        messages.error(request, "Credenciales incorrectas.")
        return render(request, "accounts/login.html", {"email": email})

    password_ok = False

    # 1) Caso: password en HASH (Django)
    try:
        if check_password(password, usuario.password):
            password_ok = True
    except Exception:
        password_ok = False

    # 2) Caso: password en TEXTO PLANO (modo legado) -> migración automática a hash
    if not password_ok and usuario.password == password:
        password_ok = True
        usuario.password = make_password(password)
        usuario.save(update_fields=["password"])

    if not password_ok:
        _register_failed_attempt(base_key, blocked_until_key, now)
        messages.error(request, "Credenciales incorrectas.")
        return render(request, "accounts/login.html", {"email": email})

    # Login OK -> limpiar intentos
    cache.delete(base_key)
    cache.delete(blocked_until_key)

    # --- (5) Regenerar la sesión al iniciar sesión ---
    request.session.cycle_key()

    # Guardar sesión
    request.session["id_usuario"] = int(usuario.id_usuario)
    request.session["usuario_nombre"] = usuario.nombre
    request.session["usuario_rol"] = (usuario.rol or "").strip()

    # --- (3) Recordarme ---
    if remember_me:
        request.session.set_expiry(REMEMBER_ME_SECONDS)
    else:
        request.session.set_expiry(0)

    # Validación de next (evita open redirect)
    next_url = request.GET.get("next") or "/"
    if not url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = "/"

    return redirect(next_url)


def _register_failed_attempt(base_key: str, blocked_until_key: str, now: int) -> None:
    attempts = cache.get(base_key, 0) + 1
    cache.set(base_key, attempts, timeout=LOGIN_BLOCK_SECONDS)

    if attempts >= MAX_LOGIN_ATTEMPTS:
        cache.set(blocked_until_key, now + LOGIN_BLOCK_SECONDS, timeout=LOGIN_BLOCK_SECONDS)


def _password_reset_token_key(token: str) -> str:
    return f"password_reset_token:{token}"


@require_http_methods(["POST"])
def logout_view(request):
    request.session.flush()
    return redirect("/login/")


@require_http_methods(["GET", "POST"])
def forgot_password_local_view(request):
    if request.method == "GET":
        return render(request, "accounts/forgot_password_local.html")

    email = (request.POST.get("email") or "").strip()
    if not email:
        messages.error(request, "Ingresa tu email.")
        return render(request, "accounts/forgot_password_local.html")

    usuario = Usuario.objects.filter(email=email, activo=True).first()
    if not usuario:
        messages.error(request, "No existe un usuario activo con ese email.")
        return render(request, "accounts/forgot_password_local.html", {"email": email})

    token = secrets.token_urlsafe(32)
    cache.set(
        _password_reset_token_key(token),
        int(usuario.id_usuario),
        timeout=RESET_PASSWORD_TOKEN_SECONDS,
    )

    reset_path = reverse("password_reset_local", kwargs={"token": token})
    reset_url = request.build_absolute_uri(reset_path)

    print(f"[RECUPERACION LOCAL] {email}: {reset_url}")

    messages.success(request, "Enlace temporal generado para pruebas locales.")
    return render(
        request,
        "accounts/forgot_password_local.html",
        {
            "email": email,
            "reset_url": reset_url,
            "expires_minutes": RESET_PASSWORD_TOKEN_SECONDS // 60,
        },
    )


@require_http_methods(["GET", "POST"])
def password_reset_local_view(request, token: str):
    cache_key = _password_reset_token_key(token)
    user_id = cache.get(cache_key)

    if not user_id:
        messages.error(request, "El enlace de recuperación no es válido o ya expiró.")
        return redirect("password_forgot_local")

    if request.method == "GET":
        return render(request, "accounts/password_reset_local.html", {"token": token})

    new_password = request.POST.get("new_password") or ""
    new_password2 = request.POST.get("new_password2") or ""

    if not new_password or not new_password2:
        messages.error(request, "Completa ambos campos.")
        return render(request, "accounts/password_reset_local.html", {"token": token})

    if new_password != new_password2:
        messages.error(request, "Las contraseñas no coinciden.")
        return render(request, "accounts/password_reset_local.html", {"token": token})

    if len(new_password) < 8:
        messages.error(request, "La contraseña debe tener al menos 8 caracteres.")
        return render(request, "accounts/password_reset_local.html", {"token": token})

    usuario = Usuario.objects.filter(id_usuario=user_id, activo=True).first()
    if not usuario:
        cache.delete(cache_key)
        messages.error(request, "No se pudo validar el usuario para recuperar contraseña.")
        return redirect("password_forgot_local")

    usuario.password = make_password(new_password)
    usuario.save(update_fields=["password"])
    cache.delete(cache_key)

    messages.success(request, "Contraseña restablecida. Ya puedes iniciar sesión.")
    return redirect("login")


# ----------- (6) Cambiar contraseña -----------

@login_required_custom
@require_http_methods(["GET", "POST"])
def change_password_view(request):
    if request.method == "GET":
        return render(request, "accounts/change_password.html")

    current_password = request.POST.get("current_password") or ""
    new_password = request.POST.get("new_password") or ""
    new_password2 = request.POST.get("new_password2") or ""

    if not current_password or not new_password or not new_password2:
        messages.error(request, "Completa todos los campos.")
        return render(request, "accounts/change_password.html")

    if new_password != new_password2:
        messages.error(request, "La nueva contraseña no coincide.")
        return render(request, "accounts/change_password.html")

    if len(new_password) < 8:
        messages.error(request, "La nueva contraseña debe tener al menos 8 caracteres.")
        return render(request, "accounts/change_password.html")

    usuario = Usuario.objects.filter(id_usuario=request.session["id_usuario"], activo=True).first()
    if not usuario or not usuario.password:
        messages.error(request, "No se pudo validar el usuario.")
        return render(request, "accounts/change_password.html")

    ok = False
    try:
        ok = check_password(current_password, usuario.password)
    except Exception:
        ok = False

    # soporte legado (texto plano)
    if not ok and usuario.password == current_password:
        ok = True

    if not ok:
        messages.error(request, "La contraseña actual es incorrecta.")
        return render(request, "accounts/change_password.html")

    usuario.password = make_password(new_password)
    usuario.save(update_fields=["password"])

    messages.success(request, "Contraseña actualizada correctamente.")
    return redirect("change_password")


# ----------- (7) Crear usuario (solo Administrador) -----------

@login_required_custom
@require_http_methods(["GET", "POST"])
def create_user_view(request):
    # Cambio clave: NO usar messages + redirect (eso ensucia login/change_password).
    # Mejor: 403 directo.
    if request.session.get("usuario_rol") != "Administrador":
        return HttpResponseForbidden("No tienes permisos para crear usuarios.")

    if request.method == "GET":
        return render(request, "accounts/create_user.html")

    nombre = (request.POST.get("nombre") or "").strip()
    email = (request.POST.get("email") or "").strip()
    password = request.POST.get("password") or ""
    rol = (request.POST.get("rol") or "").strip()
    activo = (request.POST.get("activo") == "1")

    if not nombre or not email or not password:
        messages.error(request, "Completa todos los campos obligatorios.")
        return render(
            request,
            "accounts/create_user.html",
            {"nombre": nombre, "email": email, "rol": rol, "activo": activo},
        )

    if rol not in ["Administrador", "Vendedor", "Bodeguero"]:
        messages.error(request, "Rol inválido.")
        return render(
            request,
            "accounts/create_user.html",
            {"nombre": nombre, "email": email, "rol": rol, "activo": activo},
        )

    if Usuario.objects.filter(email=email).exists():
        messages.error(request, "Ese email ya existe.")
        return render(
            request,
            "accounts/create_user.html",
            {"nombre": nombre, "email": email, "rol": rol, "activo": activo},
        )

    Usuario.objects.create(
        nombre=nombre,
        email=email,
        password=make_password(password),
        rol=rol,
        activo=activo,
    )

    messages.success(request, "Usuario creado correctamente.")
    return redirect("/")


# ----------- (8) Listar usuarios y alternar activo (solo Administrador) -----------


@login_required_custom
@require_http_methods(["GET"])
def users_list_view(request):
    if request.session.get("usuario_rol") != "Administrador":
        return HttpResponseForbidden("No tienes permisos para ver la lista de usuarios.")

    usuarios = Usuario.objects.all().order_by("id_usuario")
    current_user_id = request.session.get("id_usuario")
    try:
        current_user_id = int(current_user_id) if current_user_id is not None else None
    except (TypeError, ValueError):
        current_user_id = None

    return render(
        request,
        "accounts/users_list.html",
        {"usuarios": usuarios, "current_user_id": current_user_id},
    )


@login_required_custom
@require_http_methods(["POST"])
def toggle_user_active_view(request, id_usuario: int):
    if request.session.get("usuario_rol") != "Administrador":
        return HttpResponseForbidden("No tienes permisos para modificar usuarios.")

    usuario = Usuario.objects.filter(id_usuario=id_usuario).first()
    if not usuario:
        messages.error(request, "Usuario no existe.")
        return redirect("users_list")

    usuario.activo = not bool(usuario.activo)
    usuario.save(update_fields=["activo"])

    messages.success(request, "Estado de usuario actualizado.")
    return redirect("users_list")