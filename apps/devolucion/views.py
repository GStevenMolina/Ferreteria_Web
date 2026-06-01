# apps/devolucion/views.py

from django.shortcuts import render, redirect
from django.utils import timezone
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from apps.core.models import (
    Devolucion,
    Producto,
    Venta,
    DetalleVenta,
    Inventario,
    MovimientoInventario,
)


def obtener_productos(request, id_factura):
    """
    Devuelve en formato JSON los productos pertenecientes
    a la factura seleccionada.
    """
    productos = []

    try:
        detalles = (
            DetalleVenta.objects
            .filter(id_venta_id=id_factura)
            .select_related("id_producto")
        )

        productos_ids = set()

        for detalle in detalles:
            producto = detalle.id_producto

            if producto.id_producto not in productos_ids:
                productos.append({
                    "id": producto.id_producto,
                    "nombre": producto.nombre,
                })
                productos_ids.add(producto.id_producto)

    except Exception:
        pass

    return JsonResponse({
        "productos": productos
    })


def index(request):

    buscar = request.GET.get("buscar", "")

    devoluciones = (
        Devolucion.objects
        .select_related(
            "id_producto",
            "id_venta",
            "id_venta__id_cliente",
        )
        .order_by("-fecha")
    )

    if buscar:
        devoluciones = devoluciones.filter(
            id_producto__nombre__icontains=buscar
        )

    facturas = (
        Venta.objects
        .select_related("id_cliente")
        .order_by("-id_venta")
    )

    if request.method == "POST":

        fecha = request.POST.get("fecha")
        plazo = request.POST.get("plazo")
        condiciones = request.POST.get("condiciones")
        id_producto = request.POST.get("id_producto")
        id_factura = request.POST.get("id_factura")

        if not all([
            fecha,
            plazo,
            condiciones,
            id_producto,
            id_factura,
        ]):
            return render(request, "devolucion/index.html", {
                "error": "Todos los campos son obligatorios.",
                "devoluciones": devoluciones,
                "facturas": facturas,
                "factura_seleccionada": None,
                "productos": [],
                "today": timezone.now().date().isoformat(),
            })

        try:
            plazo = int(plazo)
        except ValueError:
            return render(request, "devolucion/index.html", {
                "error": "El plazo debe ser numérico.",
                "devoluciones": devoluciones,
                "facturas": facturas,
                "factura_seleccionada": None,
                "productos": [],
                "today": timezone.now().date().isoformat(),
            })

        # ==========================================
        # VALIDAR FECHA
        # ==========================================
        try:
            fecha_ingresada = datetime.strptime(
                fecha,
                "%Y-%m-%d"
            ).date()

            fecha_actual = timezone.now().date()

            if fecha_ingresada < fecha_actual:
                return render(request, "devolucion/index.html", {
                    "error": "La fecha no puede ser anterior al día actual.",
                    "devoluciones": devoluciones,
                    "facturas": facturas,
                    "factura_seleccionada": None,
                    "productos": [],
                    "today": timezone.now().date().isoformat(),
                })

        except ValueError:
            return render(request, "devolucion/index.html", {
                "error": "Fecha inválida.",
                "devoluciones": devoluciones,
                "facturas": facturas,
                "factura_seleccionada": None,
                "productos": [],
                "today": timezone.now().date().isoformat(),
            })

        try:
            with transaction.atomic():

                venta = Venta.objects.get(
                    id_venta=id_factura
                )

                producto = Producto.objects.get(
                    id_producto=id_producto
                )

                existe_detalle = (
                    DetalleVenta.objects
                    .filter(
                        id_venta=venta,
                        id_producto=producto
                    )
                    .exists()
                )

                if not existe_detalle:
                    raise Exception(
                        "El producto no pertenece a la factura seleccionada."
                    )

                ya_devuelto = (
                    Devolucion.objects
                    .filter(
                        id_venta=venta,
                        id_producto=producto
                    )
                    .exists()
                )

                if ya_devuelto:
                    raise Exception(
                        "Este producto ya fue devuelto."
                    )

                devolucion = Devolucion.objects.create(
                    id_venta=venta,
                    id_producto=producto,
                    fecha=fecha_ingresada,
                    plazo=plazo,
                    condiciones=condiciones,
                    estado="Aceptada"
                )

                inventario = Inventario.objects.get(
                    id_producto=producto
                )

                inventario.stock_actual += 1
                inventario.save()

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
                "facturas": facturas,
                "factura_seleccionada": None,
                "productos": [],
                "today": timezone.now().date().isoformat(),
            })

    context = {
        "devoluciones": devoluciones,
        "facturas": facturas,
        "factura_seleccionada": None,
        "productos": [],
        "today": timezone.now().date().isoformat(),
    }

    return render(
        request,
        "devolucion/index.html",
        context
    )


# ==========================================================
# REPORTE PDF DE DEVOLUCIONES
# ==========================================================
def reporte_devoluciones_pdf(request):

    devoluciones = (
        Devolucion.objects
        .select_related(
            "id_producto",
            "id_venta",
            "id_venta__id_cliente"
        )
        .order_by("-fecha")
    )

    response = HttpResponse(
        content_type='application/pdf'
    )

    response[
        'Content-Disposition'
    ] = 'attachment; filename="Reporte_Devoluciones.pdf"'

    pdf = canvas.Canvas(response, pagesize=A4)

    width, height = A4
    y = height - 50

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(
        50,
        y,
        "REPORTE DE DEVOLUCIONES"
    )

    y -= 30

    pdf.setFont("Helvetica", 10)
    pdf.drawString(
        50,
        y,
        f"Fecha: {timezone.now().strftime('%d/%m/%Y')}"
    )

    y -= 40

    pdf.setFont("Helvetica-Bold", 9)

    pdf.drawString(40, y, "Fecha")
    pdf.drawString(100, y, "Cliente")
    pdf.drawString(220, y, "Producto")
    pdf.drawString(340, y, "Plazo")
    pdf.drawString(400, y, "Factura")

    y -= 15

    pdf.line(40, y, 550, y)

    y -= 20

    pdf.setFont("Helvetica", 8)

    for d in devoluciones:

        pdf.drawString(
            40,
            y,
            d.fecha.strftime("%d/%m/%Y")
        )

        pdf.drawString(
            100,
            y,
            d.id_venta.id_cliente.nombre[:20]
        )

        pdf.drawString(
            220,
            y,
            d.id_producto.nombre[:20]
        )

        pdf.drawString(
            340,
            y,
            str(d.plazo)
        )

        pdf.drawString(
            400,
            y,
            str(d.id_venta.id_venta)
        )

        y -= 20

        if y < 50:
            pdf.showPage()
            y = height - 50

    pdf.save()

    return response