# apps/devolucion/views.py
from django.conf import settings
import os
from reportlab.lib import colors
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

    # Ordenar por ID descendente (más recientes primero)
    devoluciones = (
        Devolucion.objects
        .select_related(
            "id_producto",
            "id_venta",
            "id_venta__id_cliente",
        )
        .order_by("-id_devolucion")
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
        # VALIDAR PLAZO (no puede ser negativo ni cero)
        # ==========================================
        if plazo <= 0:
            return render(request, "devolucion/index.html", {
                "error": "El plazo debe ser un número positivo (mayor a 0).",
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


# ===============================
# REPORTE PDF DE DEVOLUCIONES
# ===============================
def reporte_devoluciones_pdf(request):

    devoluciones = (
        Devolucion.objects
        .select_related(
            "id_producto",
            "id_venta",
            "id_venta__id_cliente"
        )
        .order_by("-id_devolucion")
    )

    response = HttpResponse(
        content_type='application/pdf'
    )

    response['Content-Disposition'] = 'attachment; filename="Reporte_Devoluciones.pdf"'

    pdf = canvas.Canvas(response, pagesize=A4)

    width, height = A4

    azul = colors.HexColor("#0B4EA2")

    # ==================================
    # LOGO
    # ==================================
    logo = os.path.join(
        settings.BASE_DIR,
        "static",
        "assets",
        "Ferreteria.png"
    )

    if os.path.exists(logo):
        pdf.drawImage(
            logo,
            20,
            height - 180,
            width=290,
            height=180,
            preserveAspectRatio=True
        )

    # ==================================
    # TÍTULO Y FECHA
    # ==================================
    pdf.setLineWidth(1)

    pdf.rect(400, height - 90, 150, 30)
    pdf.rect(400, height - 120, 150, 30)

    pdf.setFont("Helvetica-Bold", 11)

    pdf.drawString(
        410,
        height - 72,
        "REPORTE DEVOLUCIONES"
    )

    pdf.drawString(
        410,
        height - 102,
        f"FECHA: {timezone.now().strftime('%d/%m/%Y')}"
    )

    # ==================================
    # DATOS EMPRESA
    # ==================================
    pdf.setFont("Helvetica-Bold", 14)

    pdf.drawString(
        40,
        height - 180,
        "DATOS DE LA EMPRESA"
    )

    pdf.setFont("Helvetica", 11)

    pdf.drawString(40, height - 205, "Dirección: Granada Diriomo, de la entrada principal")
    pdf.drawString(40, height - 220, " de Diriomo una cuadra al Norte a mano izquierda")
    pdf.drawString(40, height - 245, "Teléfono: +505 8765-4321")
    pdf.drawString(40, height - 265, "RUC/NIT: J-12345678-9")
    pdf.drawString(40, height - 280, "Email: info@ferreteriamicasa.com")

    # ==================================
    # CABECERA TABLA
    # ==================================
    tabla_y = height - 340

    pdf.setFillColor(azul)

    pdf.rect(
        40,
        tabla_y,
        510,
        25,
        fill=1
    )

    pdf.setFillColor(colors.white)

    pdf.setFont("Helvetica-Bold", 9)

    pdf.drawString(50, tabla_y + 8, "FECHA")
    pdf.drawString(110, tabla_y + 8, "CLIENTE")
    pdf.drawString(200, tabla_y + 8, "PRODUCTO")
    pdf.drawString(310, tabla_y + 8, "CONDICIONES")
    pdf.drawString(430, tabla_y + 8, "PLAZO")
    pdf.drawString(480, tabla_y + 8, "FACTURA")

    # ==================================
    # DETALLES
    # ==================================
    y = tabla_y - 25

    pdf.setFillColor(colors.black)

    pdf.setFont("Helvetica", 8)

    for d in devoluciones:

        # Si llega al final de la página, crear una nueva
        if y < 80:
            pdf.showPage()
            y = height - 50

            # Repetir encabezado en nueva página
            pdf.setFillColor(azul)
            pdf.rect(40, y, 510, 25, fill=1)

            pdf.setFillColor(colors.white)
            pdf.setFont("Helvetica-Bold", 9)

            pdf.drawString(50, y + 8, "FECHA")
            pdf.drawString(110, y + 8, "CLIENTE")
            pdf.drawString(200, y + 8, "PRODUCTO")
            pdf.drawString(310, y + 8, "CONDICIONES")
            pdf.drawString(430, y + 8, "PLAZO")
            pdf.drawString(480, y + 8, "FACTURA")

            y -= 25
            pdf.setFillColor(colors.black)
            pdf.setFont("Helvetica", 8)

        pdf.rect(40, y, 510, 25)

        pdf.drawString(
            50,
            y + 8,
            d.fecha.strftime("%d/%m/%Y")
        )

        pdf.drawString(
            110,
            y + 8,
            d.id_venta.id_cliente.nombre[:15]
        )

        pdf.drawString(
            200,
            y + 8,
            d.id_producto.nombre[:15]
        )

        # ← CAMPO condiciones
        pdf.drawString(
            310,
            y + 8,
            d.condiciones[:20] if d.condiciones else "N/A"
        )

        pdf.drawString(
            430,
            y + 8,
            str(d.plazo)
        )

        pdf.drawString(
            480,
            y + 8,
            str(d.id_venta.id_venta)
        )

        y -= 25

    # ==================================
    # PIE
    # ==================================
    pdf.setFillColor(azul)

    pdf.rect(
        0,
        0,
        width,
        35,
        fill=1
    )

    pdf.setFillColor(colors.white)

    pdf.setFont(
        "Helvetica-Bold",
        12
    )

    pdf.drawString(
        40,
        12,
        "www.ferreteriamicasa.NotenemosDominio.XD"
    )

    pdf.drawRightString(
        width - 40,
        12,
        "REPORTE DE DEVOLUCIONES"
    )

    pdf.save()

    return response
