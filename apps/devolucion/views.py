from django.shortcuts import render, redirect
from django.utils import timezone
from django.db import transaction

from apps.core.models import (
    Devolucion,
    Producto,
    Venta,
    Cliente,
    DetalleVenta,
    Inventario,
    MovimientoInventario
)


def index(request):

    # ===== BUSCADOR =====
    buscar = request.GET.get("buscar")

    devoluciones = Devolucion.objects.select_related(
        "id_producto",
        "id_venta"
    ).all().order_by("-fecha")

    # ===== FILTRAR POR PRODUCTO =====
    if buscar:
        devoluciones = devoluciones.filter(
            id_producto__nombre__icontains=buscar
        )

    # ===== DATOS PARA EL FORMULARIO =====
    clientes = Cliente.objects.all().order_by("nombre")
    productos = Producto.objects.all().order_by("nombre")

    # ===== REGISTRAR DEVOLUCIÓN =====
    if request.method == "POST":

        fecha = request.POST.get("fecha")
        plazo = request.POST.get("plazo")
        condiciones = request.POST.get("condiciones")

        # FORM
        id_cliente = request.POST.get("id_cliente")
        id_producto = request.POST.get("id_producto")

        # ===== VALIDACIONES =====
        if not all([
            fecha,
            plazo,
            condiciones,
            id_cliente,
            id_producto
        ]):
            return render(request, "devolucion/index.html", {
                "error": "Todos los campos son obligatorios",
                "devoluciones": devoluciones,
                "clientes": clientes,
                "productos": productos
            })

        try:
            plazo = int(plazo)

        except:
            return render(request, "devolucion/index.html", {
                "error": "El plazo debe ser numérico",
                "devoluciones": devoluciones,
                "clientes": clientes,
                "productos": productos
            })

        try:
            with transaction.atomic():

                # ===== CLIENTE =====
                cliente = Cliente.objects.get(
                    id_cliente=id_cliente
                )

                # ===== PRODUCTO =====
                producto = Producto.objects.get(
                    id_producto=id_producto
                )

                # ===== BUSCAR ÚLTIMA VENTA DEL CLIENTE =====
                venta = Venta.objects.filter(
                    id_cliente=cliente
                ).order_by("-id_venta").first()

                # ===== VALIDAR VENTA =====
                if not venta:
                    return render(request, "devolucion/index.html", {
                        "error": "El cliente no tiene ventas registradas",
                        "devoluciones": devoluciones,
                        "clientes": clientes,
                        "productos": productos
                    })

                # ===== VALIDAR PRODUCTO EN ESA VENTA =====
                existe_detalle = DetalleVenta.objects.filter(
                    id_venta=venta,
                    id_producto=producto
                ).exists()

                if not existe_detalle:
                    return render(request, "devolucion/index.html", {
                        "error": "Ese producto no pertenece a la última factura del cliente",
                        "devoluciones": devoluciones,
                        "clientes": clientes,
                        "productos": productos
                    })

                # ===== VALIDAR DEVOLUCIÓN DUPLICADA =====
                ya_devuelto = Devolucion.objects.filter(
                    id_venta=venta,
                    id_producto=producto
                ).exists()

                if ya_devuelto:
                    return render(request, "devolucion/index.html", {
                        "error": "Este producto ya fue devuelto",
                        "devoluciones": devoluciones,
                        "clientes": clientes,
                        "productos": productos
                    })

                # ===== REGISTRAR DEVOLUCIÓN =====
                devolucion = Devolucion.objects.create(
                    id_venta=venta,
                    id_producto=producto,
                    fecha=fecha,
                    plazo=plazo,
                    condiciones=condiciones,
                    estado="Aceptada"
                )

                # ===== ACTUALIZAR INVENTARIO =====
                inventario = Inventario.objects.get(
                    id_producto=producto
                )

                inventario.stock_actual += 1
                inventario.save()

                # ===== MOVIMIENTO INVENTARIO =====
                MovimientoInventario.objects.create(
                    id_producto=producto,
                    tipo_movimiento="ENTRADA",
                    cantidad=1,
                    referencia=f"Devolución #{devolucion.id_devolucion}",
                    fecha_movimiento=timezone.now()
                )

                return redirect("devolucion:index")

        except Exception as e:

            return render(request, "devolucion/index.html", {
                "error": str(e),
                "devoluciones": devoluciones,
                "clientes": clientes,
                "productos": productos
            })

    return render(request, "devolucion/index.html", {
        "devoluciones": devoluciones,
        "clientes": clientes,
        "productos": productos
    })