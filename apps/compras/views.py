from django.shortcuts import render
from django.http import HttpResponse
from apps.accounts.auth import login_required_custom

@login_required_custom
def nueva_compra(request):
    id_usuario = request.session["id_usuario"]  # aquí ya existe seguro
    return HttpResponse(f"Comprando como usuario #{id_usuario}")

def index(request):
    return render(request, "compras/index.html")