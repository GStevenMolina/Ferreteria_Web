from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from apps.core.models import Usuario

@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == "GET":
        if request.session.get("id_usuario"):
            return redirect("/")
        return render(request, "accounts/login.html")

    email = (request.POST.get("email") or "").strip()
    password = request.POST.get("password") or ""

    if not email or not password:
        messages.error(request, "Email y contraseña son requeridos.")
        return render(request, "accounts/login.html", {"email": email})

    usuario = Usuario.objects.filter(email=email, activo=True).first()
    if not usuario or usuario.password != password:
        messages.error(request, "Credenciales incorrectas.")
        return render(request, "accounts/login.html", {"email": email})

    request.session["id_usuario"] = int(usuario.id_usuario)
    request.session["usuario_nombre"] = usuario.nombre

    next_url = request.GET.get("next") or "/"
    return redirect(next_url)

@require_http_methods(["GET", "POST"])
def logout_view(request):
    request.session.flush()
    return redirect("/login/")