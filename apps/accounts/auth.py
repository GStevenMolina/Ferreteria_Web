from functools import wraps
from django.shortcuts import redirect
from django.http import HttpResponseForbidden


def login_required_custom(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.session.get("id_usuario"):
            return redirect(f"/login/?next={request.get_full_path()}")
        return view_func(request, *args, **kwargs)
    return _wrapped


def roles_required(allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            rol = request.session.get("usuario_rol")
            if rol not in allowed_roles:
                return HttpResponseForbidden("No tienes permisos para acceder a esta sección.")
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator