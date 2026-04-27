#```python name=apps/accounts/auth.py
from functools import wraps
from django.shortcuts import redirect

def login_required_custom(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.session.get("id_usuario"):
            return redirect(f"/login/?next={request.get_full_path()}")
        return view_func(request, *args, **kwargs)
    return _wrapped