from django.shortcuts import render, redirect
from django.utils import timezone
from django.db import transaction
from decimal import Decimal

from apps.core.models import (
    Devolucion, Producto, Venta, DetalleVenta,
    Inventario, MovimientoInventario
)


def index(request):
    devoluciones = Devolucion.objects.select_related(
        "id_producto", "id_venta"
    ).all().order_by("-fecha")

    if request.method == "POST":

        fecha = request.POST.get("fecha")
        plazo = request.POST.get("plazo")
        condiciones = request.POST.get("condiciones")
        nombre_producto = request.POST.get("producto")

        # 🔴 VALIDACIONES
        if not all([fecha, plazo, condiciones, nombre_producto]):
            return render(request, "devolucion/index.html", {
                "error": "Todos los campos son obligatorios",
                "devoluciones": devoluciones
            })

        try:
            plazo = int(plazo)
        except:
            return render(request, "devolucion/index.html", {
                "error": "El plazo debe ser numérico",
                "devoluciones": devoluciones
            })

        try:
            with transaction.atomic():

                # 🔍 BUSCAR PRODUCTO
                producto = Producto.objects.filter(
                    nombre__icontains=nombre_producto
                ).first()

                if not producto:
                    return render(request, "devolucion/index.html", {
                        "error": "Producto no encontrado",
                        "devoluciones": devoluciones
                    })

                # 🔍 BUSCAR ÚLTIMA VENTA DEL PRODUCTO
                detalle = DetalleVenta.objects.filter(
                    id_producto=producto
                ).order_by("-id_venta__id_venta").first()

                if not detalle:
                    return render(request, "devolucion/index.html", {
                        "error": "El producto no tiene ventas registradas",
                        "devoluciones": devoluciones
                    })

                venta = detalle.id_venta

                # 🔴 VALIDAR SI YA FUE DEVUELTO
                ya_devuelto = Devolucion.objects.filter(
                    id_venta=venta,
                    id_producto=producto
                ).exists()

                if ya_devuelto:
                    return render(request, "devolucion/index.html", {
                        "error": "Este producto ya fue devuelto",
                        "devoluciones": devoluciones
                    })

                # 🔄 REGISTRAR DEVOLUCIÓN
                devolucion = Devolucion.objects.create(
                    id_venta=venta,
                    id_producto=producto,
                    fecha=fecha,
                    plazo=plazo,
                    condiciones=condiciones,
                    estado="Aceptada"
                )

                # 📦 ACTUALIZAR INVENTARIO (DEVOLUCIÓN = ENTRADA)
                inventario = Inventario.objects.get(id_producto=producto)
                inventario.stock_actual += 1  # puedes ajustar cantidad si quieres
                inventario.save()

                # 📊 MOVIMIENTO INVENTARIO
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
                "devoluciones": devoluciones
            })

    return render(request, "devolucion/index.html", {
        "devoluciones": devoluciones
    })