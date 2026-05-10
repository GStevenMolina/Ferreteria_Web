from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.core.mail import send_mail
from django.core.cache import cache
from django.urls import reverse
from django.contrib.auth.hashers import make_password, check_password
import random

from apps.core.models import Usuario

RESET_PASSWORD_CODE_SECONDS = 15 * 60  # 15 minutos

# --- INICIO DE SESIÓN ---
@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == "GET":
        return render(request, "accounts/login.html")

    email = (request.POST.get("email") or "").strip()
    password = request.POST.get("password") or ""

    if not email or not password:
        messages.error(request, "Email y contraseña son requeridos.")
        return render(request, "accounts/login.html", {"email": email})

    usuario = Usuario.objects.filter(email=email, activo=True).first()
    if not usuario or not usuario.password:
        messages.error(request, "Credenciales incorrectas.")
        return render(request, "accounts/login.html", {"email": email})

    # Compatibilidad con hash y texto plano
    password_ok = False
    try:
        if check_password(password, usuario.password):
            password_ok = True
    except Exception:
        password_ok = False
    if not password_ok and usuario.password == password:
        password_ok = True
        usuario.password = make_password(password)
        usuario.save(update_fields=["password"])

    if not password_ok:
        messages.error(request, "Credenciales incorrectas.")
        return render(request, "accounts/login.html", {"email": email})

    # Si todo ok, guardar info en sesión
    request.session["id_usuario"] = int(usuario.id_usuario)
    request.session["usuario_nombre"] = usuario.nombre
    request.session["usuario_rol"] = (usuario.rol or "").strip()

    # Recuerda (opcional)
    remember_me = request.POST.get("remember_me") == "1"
    if remember_me:
        request.session.set_expiry(60 * 60 * 24 * 7)  # 7 días
    else:
        request.session.set_expiry(0)

    return redirect("/")

# --- LOGOUT ---
@require_http_methods(["GET", "POST"])
def logout_view(request):
    request.session.flush()
    return redirect("login")

# --- Recuperación de contraseña: Paso 1 - Solicita email, envía código ---
@require_http_methods(["GET", "POST"])
def forgot_password_code(request):
    if request.method == "GET":
        return render(request, "accounts/forgot_password_code.html")

    email = (request.POST.get("email") or "").strip()
    if not email:
        messages.error(request, "Ingresa tu email.")
        return render(request, "accounts/forgot_password_code.html")

    usuario = Usuario.objects.filter(email=email, activo=True).first()
    if not usuario:
        messages.error(request, "No existe un usuario activo con ese email.")
        return render(request, "accounts/forgot_password_code.html", {"email": email})

    code = str(random.randint(100000, 999999))
    cache.set(f"password_reset_code_{email}", code, timeout=RESET_PASSWORD_CODE_SECONDS)

    send_mail(
        "Código de recuperación de contraseña",
        f"Tu código de verificación es: {code}\n(Expira en 15 minutos)",
        None,
        [email],
        fail_silently=False,
    )

    messages.success(request, "El código de recuperación fue enviado a tu correo.")
    request.session["recover_email"] = email
    return redirect("password_reset_code_verify")

# --- Recuperación de contraseña: Paso 2 - Código y nueva contraseña ---
@require_http_methods(["GET", "POST"])
def password_reset_code_verify(request):
    email = request.session.get("recover_email")
    if not email:
        messages.error(request, "Primero solicita la recuperación de contraseña.")
        return redirect("password_forgot")   # <- ESTA LINEA ARREGLADA

    if request.method == "GET":
        return render(request, "accounts/password_reset_code_verify.html", {"email": email})

    code = (request.POST.get("code") or "").strip()
    new_password = request.POST.get("new_password") or ""
    new_password2 = request.POST.get("new_password2") or ""

    if not code or not new_password or not new_password2:
        messages.error(request, "Completa todos los campos.")
        return render(request, "accounts/password_reset_code_verify.html", {"email": email})

    if new_password != new_password2:
        messages.error(request, "Las contraseñas no coinciden.")
        return render(request, "accounts/password_reset_code_verify.html", {"email": email})

    if len(new_password) < 8:
        messages.error(request, "La nueva contraseña debe tener al menos 8 caracteres.")
        return render(request, "accounts/password_reset_code_verify.html", {"email": email})

    cached_code = cache.get(f"password_reset_code_{email}")
    if not cached_code or code != cached_code:
        messages.error(request, "El código es incorrecto o expiró.")
        return render(request, "accounts/password_reset_code_verify.html", {"email": email})

    usuario = Usuario.objects.filter(email=email, activo=True).first()
    if not usuario:
        cache.delete(f"password_reset_code_{email}")
        messages.error(request, "No se pudo validar el usuario.")
        return redirect("password_forgot")   # <- ESTA LINEA ARREGLADA

    usuario.password = make_password(new_password)
    usuario.save(update_fields=["password"])
    cache.delete(f"password_reset_code_{email}")
    del request.session["recover_email"]

    messages.success(request, "Contraseña restablecida. Ya puedes iniciar sesión.")
    return redirect("login")

# --- LISTADO DE USUARIOS ---
@require_http_methods(["GET"])
def users_list_view(request):
    usuarios = Usuario.objects.all()
    return render(request, "accounts/users_list.html", {"usuarios": usuarios})

# --- CREAR USUARIO ---
@require_http_methods(["GET", "POST"])
def create_user_view(request):
    if request.method == "GET":
        return render(request, "accounts/create_user.html")

    nombre = (request.POST.get("nombre") or "").strip()
    email = (request.POST.get("email") or "").strip()
    password = request.POST.get("password") or ""
    rol = (request.POST.get("rol") or "").strip()
    activo = request.POST.get("activo") == "1"

    if not nombre or not email or not password:
        messages.error(request, "Nombre, email y contraseña son requeridos.")
        return render(request, "accounts/create_user.html", {
            "nombre": nombre,
            "email": email,
            "rol": rol,
            "activo": activo,
        })

    if Usuario.objects.filter(email=email).exists():
        messages.error(request, "El email ya está registrado.")
        return render(request, "accounts/create_user.html", {
            "nombre": nombre,
            "email": email,
            "rol": rol,
            "activo": activo,
        })

    usuario = Usuario.objects.create(
        nombre=nombre,
        email=email,
        password=make_password(password),
        rol=rol,
        activo=activo,
    )
    messages.success(request, f"Usuario '{nombre}' creado exitosamente.")
    return redirect("users_list")

# --- TOGGLE ESTADO DE USUARIO ---
@require_http_methods(["POST"])
def toggle_user_active_view(request, id_usuario):
    try:
        usuario = Usuario.objects.get(id_usuario=id_usuario)
        usuario.activo = not usuario.activo
        usuario.save(update_fields=["activo"])
        estado = "activado" if usuario.activo else "desactivado"
        messages.success(request, f"Usuario '{usuario.nombre}' {estado}.")
    except Usuario.DoesNotExist:
        messages.error(request, "Usuario no encontrado.")
    
    return redirect("users_list")