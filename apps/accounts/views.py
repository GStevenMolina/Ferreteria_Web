from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.core.mail import send_mail
from django.core.cache import cache
from django.urls import reverse
from django.contrib.auth.hashers import make_password, check_password
import random
from datetime import timedelta
from django.utils import timezone

from apps.core.models import Usuario
from apps.core.models import Auditoria

RESET_PASSWORD_CODE_SECONDS = 15 * 60  # 15 minutos

# --- Configuración de BLOQUEO ---
MAX_FAILED_ATTEMPTS = 5                # intentos permitidos
BLOCK_TIME_SECONDS = 10 * 60           # 10 minutos bloqueado


def _is_admin_session(request):
    return (request.session.get("usuario_rol") or "").strip() == "Administrador"


def _require_admin_session(request):
    if not request.session.get("id_usuario"):
        return redirect(reverse("login"))

    if not _is_admin_session(request):
        messages.error(request, "No tienes permisos para acceder a esa sección.")
        return redirect("/")

    return None

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
    ip = request.META.get("REMOTE_ADDR")
    exito = False

    # --- BLOQUEO POR INTENTOS FALLIDOS ---
    bloqueado = False
    bloqueado_key = f"login_blocked_{email}"
    failed_attempts_key = f"login_failed_{email}"

    # ¿Está bloqueado por demasiados intentos fallidos?
    if cache.get(bloqueado_key):
        bloqueado = True

    if bloqueado:
        messages.error(
            request,
            "Tu cuenta ha sido temporalmente bloqueada por múltiples intentos fallidos. Inténtalo de nuevo en unos minutos."
        )
        Auditoria.objects.create(usuario=usuario, email=email, exito=False, ip=ip)
        return render(request, "accounts/login.html", {"email": email})

    if not usuario or not usuario.password:
        # registra intento fallido
        Auditoria.objects.create(usuario=None, email=email, exito=exito, ip=ip)
        # incrementa contador de fallos
        fails = cache.get(failed_attempts_key, 0) + 1
        cache.set(failed_attempts_key, fails, timeout=BLOCK_TIME_SECONDS)
        # bloquea si ha excedido los intentos
        if fails >= MAX_FAILED_ATTEMPTS:
            cache.set(bloqueado_key, True, timeout=BLOCK_TIME_SECONDS)
            messages.error(
                request,
                "Tu cuenta ha sido bloqueada por múltiples intentos fallidos. Intenta más tarde."
            )
        else:
            messages.error(request, f"Credenciales incorrectas. Intentos restantes: {MAX_FAILED_ATTEMPTS - fails}")
        return render(request, "accounts/login.html", {"email": email})

    password_ok = False
    try:
        if check_password(password, usuario.password):
            password_ok = True
    except Exception:
        password_ok = False

    # Migración automática de contraseñas antiguas en texto plano
    if not password_ok and usuario.password == password:
        password_ok = True
        usuario.password = make_password(password)
        usuario.save(update_fields=["password"])

    if not password_ok:
        Auditoria.objects.create(usuario=usuario, email=email, exito=False, ip=ip)
        fails = cache.get(failed_attempts_key, 0) + 1
        cache.set(failed_attempts_key, fails, timeout=BLOCK_TIME_SECONDS)
        if fails >= MAX_FAILED_ATTEMPTS:
            cache.set(bloqueado_key, True, timeout=BLOCK_TIME_SECONDS)
            messages.error(request, "Tu cuenta ha sido bloqueada por múltiples intentos fallidos. Intenta más tarde.")
        else:
            messages.error(request, f"Credenciales incorrectas. Intentos restantes: {MAX_FAILED_ATTEMPTS - fails}")
        return render(request, "accounts/login.html", {"email": email})

    # Correcto: reinicia contador de fallos
    cache.delete(failed_attempts_key)
    cache.delete(bloqueado_key)

    # --- Inicio de sesión exitoso, guardar en sesión y auditar
    request.session["id_usuario"] = int(usuario.id_usuario)
    request.session["usuario_nombre"] = usuario.nombre
    request.session["usuario_rol"] = (usuario.rol or "").strip()
    Auditoria.objects.create(usuario=usuario, email=email, exito=True, ip=ip)

    # --- Expiración de sesión controlada (Se complementa con settings.py) ---
    remember_me = request.POST.get("remember_me") == "1"
    if remember_me:
        request.session.set_expiry(60 * 60 * 24 * 7)  # 7 días
    else:
        request.session.set_expiry(60 * 60)  # 60 min después del login, y se renueva cada request (config global en settings)

    return redirect("/")


@require_http_methods(["POST", "GET"])
def logout_view(request):
    request.session.flush()
    messages.success(request, "Sesión cerrada correctamente.")
    return redirect(reverse("login"))


@require_http_methods(["GET", "POST"])
def forgot_password_code(request):
    if request.method == "GET":
        return render(request, "accounts/forgot_password_code.html")

    email = (request.POST.get("email") or "").strip()
    if not email:
        messages.error(request, "Ingresa un correo válido.")
        return render(request, "accounts/forgot_password_code.html", {"email": email})

    usuario = Usuario.objects.filter(email=email, activo=True).first()
    if not usuario:
        messages.error(request, "Si el correo existe, se enviará un código de recuperación.")
        return render(request, "accounts/forgot_password_code.html", {"email": email})

    code = f"{random.randint(0, 999999):06d}"
    cache_key = f"password_reset_code_{email.lower()}"
    cache.set(cache_key, code, timeout=RESET_PASSWORD_CODE_SECONDS)
    request.session["password_reset_email"] = email

    send_mail(
        subject="Código de recuperación de contraseña",
        message=f"Tu código de recuperación es: {code}",
        from_email=None,
        recipient_list=[email],
        fail_silently=True,
    )

    messages.success(request, "Si el correo existe, se enviará un código de recuperación.")
    return redirect(reverse("password_reset_code_verify"))


@require_http_methods(["GET", "POST"])
def password_reset_code_verify(request):
    if request.method == "GET":
        return render(request, "accounts/password_reset_code_verify.html")

    email = request.session.get("password_reset_email")
    if not email:
        messages.error(request, "Primero solicita un código de recuperación.")
        return redirect(reverse("password_forgot"))

    code = (request.POST.get("code") or "").strip()
    new_password = request.POST.get("new_password") or ""
    new_password2 = request.POST.get("new_password2") or ""

    if not code or not new_password or not new_password2:
        messages.error(request, "Completa el código y la nueva contraseña.")
        return render(request, "accounts/password_reset_code_verify.html")

    if new_password != new_password2:
        messages.error(request, "Las contraseñas no coinciden.")
        return render(request, "accounts/password_reset_code_verify.html")

    cache_key = f"password_reset_code_{email.lower()}"
    expected_code = cache.get(cache_key)
    if not expected_code or expected_code != code:
        messages.error(request, "El código es inválido o expiró.")
        return render(request, "accounts/password_reset_code_verify.html")

    usuario = Usuario.objects.filter(email=email).first()
    if not usuario:
        messages.error(request, "No se encontró el usuario asociado al correo.")
        return redirect(reverse("password_forgot"))

    usuario.password = make_password(new_password)
    usuario.save(update_fields=["password"])
    cache.delete(cache_key)
    request.session.pop("password_reset_email", None)

    messages.success(request, "Tu contraseña fue actualizada correctamente.")
    return redirect(reverse("login"))


@require_http_methods(["GET"])
def users_list_view(request):
    denied = _require_admin_session(request)
    if denied:
        return denied

    usuarios = Usuario.objects.all().order_by("id_usuario")
    return render(request, "accounts/users_list.html", {"usuarios": usuarios})


@require_http_methods(["GET", "POST"])
def create_user_view(request):
    denied = _require_admin_session(request)
    if denied:
        return denied

    if request.method == "GET":
        return render(request, "accounts/create_user.html")

    nombre = (request.POST.get("nombre") or "").strip()
    email = (request.POST.get("email") or "").strip()
    password = request.POST.get("password") or ""
    rol = (request.POST.get("rol") or "").strip()
    activo = request.POST.get("activo") == "1"

    if not nombre or not email or not password or not rol:
        messages.error(request, "Completa todos los campos obligatorios.")
        return render(request, "accounts/create_user.html", {
            "nombre": nombre,
            "email": email,
            "rol": rol,
            "activo": activo,
        })

    if Usuario.objects.filter(email=email).exists():
        messages.error(request, "Ya existe un usuario con ese correo.")
        return render(request, "accounts/create_user.html", {
            "nombre": nombre,
            "email": email,
            "rol": rol,
            "activo": activo,
        })

    Usuario.objects.create(
        nombre=nombre,
        email=email,
        password=make_password(password),
        rol=rol,
        activo=activo,
        fecha_creacion=timezone.now(),
    )
    messages.success(request, "Usuario creado correctamente.")
    return redirect(reverse("users_list"))


@require_http_methods(["POST"])
def toggle_user_active_view(request, id_usuario):
    denied = _require_admin_session(request)
    if denied:
        return denied

    current_user_id = int(request.session.get("id_usuario") or 0)
    if current_user_id == int(id_usuario):
        messages.error(request, "No puedes cambiar tu propio estado desde aquí.")
        return redirect(reverse("users_list"))

    usuario = Usuario.objects.filter(id_usuario=id_usuario).first()
    if not usuario:
        messages.error(request, "Usuario no encontrado.")
        return redirect(reverse("users_list"))

    usuario.activo = not bool(usuario.activo)
    usuario.save(update_fields=["activo"])
    messages.success(request, "Estado del usuario actualizado.")
    return redirect(reverse("users_list"))


@require_http_methods(["POST"])
def edit_user_view(request, id_usuario):
    denied = _require_admin_session(request)
    if denied:
        return denied

    usuario = Usuario.objects.filter(id_usuario=id_usuario).first()
    if not usuario:
        messages.error(request, "Usuario no encontrado.")
        return redirect(reverse("users_list"))

    nombre = (request.POST.get("nombre") or "").strip()
    email = (request.POST.get("email") or "").strip()
    rol = (request.POST.get("rol") or "").strip()
    activo = request.POST.get("activo") == "1"

    if not nombre or not email or not rol:
        messages.error(request, "Completa nombre, email y rol.")
        return redirect(reverse("users_list"))

    if Usuario.objects.exclude(id_usuario=id_usuario).filter(email=email).exists():
        messages.error(request, "Ya existe otro usuario con ese correo.")
        return redirect(reverse("users_list"))

    usuario.nombre = nombre
    usuario.email = email
    usuario.rol = rol
    usuario.activo = activo
    usuario.save(update_fields=["nombre", "email", "rol", "activo"])

    messages.success(request, "Usuario actualizado correctamente.")
    return redirect(reverse("users_list"))


@require_http_methods(["GET"])
def auditoria_list_view(request):
    denied = _require_admin_session(request)
    if denied:
        return denied

    # filtros opcionales
    q_user = (request.GET.get("user") or "").strip()
    q_email = (request.GET.get("email") or "").strip()
    q_result = request.GET.get("result")  # 'ok' | 'fail' | None

    logs = Auditoria.objects.all()
    if q_user:
        logs = logs.filter(usuario__nombre__icontains=q_user)
    if q_email:
        logs = logs.filter(email__icontains=q_email)
    if q_result == 'ok':
        logs = logs.filter(exito=True)
    elif q_result == 'fail':
        logs = logs.filter(exito=False)

    logs = logs.order_by('-fecha')[:1000]

    # resumen básico
    resumen = {
        'total': Auditoria.objects.count(),
        'exitos': Auditoria.objects.filter(exito=True).count(),
        'fallos': Auditoria.objects.filter(exito=False).count(),
    }

    return render(request, "accounts/auditoria_list.html", {"logs": logs, "resumen": resumen})