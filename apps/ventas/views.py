from django.shortcuts import render, redirect
from django.utils import timezone
from decimal import Decimal
from django.db import transaction
from django.http import JsonResponse
from apps.core.models import (
    Producto, Cliente, Venta, DetalleVenta,
    Inventario, MovimientoInventario, FacturaCliente, Usuario
)

def index(request):
    carrito = request.session.get("carrito", [])
    cliente = request.session.get("cliente", None)

    if request.method == "POST":
        accion = request.POST.get("accion")

        # --- BUSCAR CLIENTE ---
        if accion == "buscar_cliente":
            nombre = request.POST.get("nombre")
            c = Cliente.objects.filter(nombre__icontains=nombre).first()
            request.session["cliente"] = None if not c else {
                "id": c.id_cliente, "nombre": c.nombre,
                "telefono": c.telefono, "direccion": c.direccion
            }
            return redirect("ventas:index")

        # --- AGREGAR CLIENTE ---
        if accion == "agregar_cliente":
            c = Cliente.objects.create(
                nombre=request.POST.get("nombre"),
                telefono=request.POST.get("telefono"),
                direccion=request.POST.get("direccion"),
                fecha_registro=timezone.now()
            )
            request.session["cliente"] = {
                "id": c.id_cliente, "nombre": c.nombre,
                "telefono": c.telefono, "direccion": c.direccion
            }
            return redirect("ventas:index")

        # --- AGREGAR PRODUCTO ---
        if accion == "agregar_producto":
            producto = Producto.objects.get(id_producto=request.POST.get("producto_id"))
            cantidad = int(request.POST.get("cantidad"))
            
            for item in carrito:
                if item["id"] == producto.id_producto:
                    item["cantidad"] += cantidad
                    item["subtotal"] = float(item["cantidad"]) * float(item["precio"])
                    break
            else:
                carrito.append({
                    "id": producto.id_producto, "nombre": producto.nombre,
                    "precio": float(producto.precio_venta), "cantidad": cantidad,
                    "subtotal": float(producto.precio_venta) * cantidad
                })
            request.session["carrito"] = carrito
            return redirect("ventas:index")

        # --- FINALIZAR VENTA (¡AHORA SÍ REGISTRA!) ---
        if accion == "finalizar":
            if not carrito or not cliente:
                return redirect("ventas:index")
            
            try:
                with transaction.atomic():
                    # 1. Obtener objetos reales de BD
                    cliente_obj = Cliente.objects.get(id_cliente=cliente['id'])
                    usuario = Usuario.objects.first() # Ajustar según tu auth
                    total_venta = sum(item["subtotal"] for item in carrito)

                    # 2. Crear la Venta
                    nueva_venta = Venta.objects.create(
                        id_cliente=cliente_obj,
                        id_usuario=usuario,
                        fecha=timezone.now(),
                        total=total_venta
                    )

                    # 3. Procesar cada item
                    for item in carrito:
                        prod = Producto.objects.get(id_producto=item["id"])
                        inv = Inventario.objects.get(id_producto=prod)

                        if inv.stock_actual < item["cantidad"]:
                            raise Exception(f"No hay suficiente stock de {prod.nombre}")

                        # Detalle de Venta
                        DetalleVenta.objects.create(
                            id_venta=nueva_venta,
                            id_producto=prod,
                            cantidad=item["cantidad"],
                            precio_unitario=item["precio"],
                            subtotal=item["subtotal"]
                        )

                        # Actualizar Stock
                        inv.stock_actual -= item["cantidad"]
                        inv.save()

                        # Registrar movimiento
                        MovimientoInventario.objects.create(
                            id_producto=prod, id_usuario=usuario,
                            tipo_movimiento="SALIDA", cantidad=item["cantidad"],
                            referencia=f"Venta #{nueva_venta.id_venta}",
                            fecha_movimiento=timezone.now()
                        )

                # Limpiar sesión solo si todo salió bien
                request.session["carrito"] = []
                request.session["cliente"] = None
                return redirect("ventas:index")

            except Exception as e:
                # Aquí podrías pasar el error al template
                return render(request, "ventas/index.html", {"error": str(e), "carrito": carrito})

    return render(request, "ventas/index.html", {
        "carrito": carrito, "cliente": cliente,
        "productos": Producto.objects.all(),
        "total": sum(item["subtotal"] for item in carrito)
    })

# Vista para AJAX
def eliminar_ajax(request, producto_id):
    if request.method == "POST":
        carrito = request.session.get("carrito", [])
        nuevo_carrito = [item for item in carrito if item["id"] != int(producto_id)]
        request.session["carrito"] = nuevo_carrito
        request.session.modified = True
        nuevo_total = sum(item["subtotal"] for item in nuevo_carrito)
        return JsonResponse({"status": "success", "nuevo_total": nuevo_total})