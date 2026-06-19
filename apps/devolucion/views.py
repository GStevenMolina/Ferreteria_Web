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
    a la factura seleccionada, permitiendo devoluciones parciales sucesivas
    calculando correctamente el saldo disponible sobre la columna 'cantidad'.
    """
    productos = []
    try:
        detalles = (
            DetalleVenta.objects
            .filter(id_venta_id=id_factura)
            .select_related("id_producto")
        )

        for detalle in detalles:
            producto = detalle.id_producto
            
            # Buscamos cuántas unidades ya se han devuelto sumando el campo real de la BD 'cantidad'
            devoluciones_previas = Devolucion.objects.filter(
                id_venta_id=id_factura, 
                id_producto=producto
            )
            
            total_devueltos = sum(d.cantidad for d in devoluciones_previas)
            
            # Cantidad que resta por devolver
            disponible = detalle.cantidad - total_devueltos

            # El producto SOLO se listará si aún le quedan unidades disponibles para devolver
            if disponible > 0:
                productos.append({
                    "id": producto.id_producto,
                    "nombre": producto.nombre,
                    "max_cantidad": disponible,  # Envía el tope real al JS (ej. 25 si ya devolvió 5 de 30)
                })
    except Exception as e:
        print(f"Error en obtener_productos: {str(e)}")
        pass

    return JsonResponse({"productos": productos})


def index(request):
    buscar = request.GET.get("buscar", "")

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
        devoluciones = devoluciones.filter(id_producto__nombre__icontains=buscar)

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
        cantidad_devolver = request.POST.get("cantidad")

        if not all([fecha, plazo, condiciones, id_producto, id_factura, cantidad_devolver]):
            return render(request, "devolucion/index.html", {
                "error": "Todos los campos son obligatorios, incluida la cantidad.",
                "devoluciones": devoluciones,
                "facturas": facturas,
                "today": timezone.now().date().isoformat(),
            })

        # Validar enteros
        try:
            plazo = int(plazo)
            cantidad_devolver = int(cantidad_devolver)
        except ValueError:
            return render(request, "devolucion/index.html", {
                "error": "El plazo y la cantidad deben ser valores numéricos.",
                "devoluciones": devoluciones,
                "facturas": facturas,
                "today": timezone.now().date().isoformat(),
            })

        if plazo <= 0 or cantidad_devolver <= 0:
            return render(request, "devolucion/index.html", {
                "error": "El plazo y la cantidad deben ser mayores a 0.",
                "devoluciones": devoluciones,
                "facturas": facturas,
                "today": timezone.now().date().isoformat(),
            })

        # Validar fecha
        try:
            fecha_ingresada = datetime.strptime(fecha, "%Y-%m-%d").date()
            if fecha_ingresada < timezone.now().date():
                raise ValueError()
        except ValueError:
            return render(request, "devolucion/index.html", {
                "error": "Fecha inválida o anterior al día actual.",
                "devoluciones": devoluciones,
                "facturas": facturas,
                "today": timezone.now().date().isoformat(),
            })

        try:
            with transaction.atomic():
                venta = Venta.objects.get(id_venta=id_factura)
                producto = Producto.objects.get(id_producto=id_producto)

                # 1. Obtener el detalle de la venta original
                detalle_venta = DetalleVenta.objects.filter(
                    id_venta=venta, 
                    id_producto=producto
                ).first()

                if not detalle_venta:
                    raise Exception("El producto no pertenece a la factura seleccionada.")

                # 2. Calcular cuántas unidades ya se devolvieron previamente de esta factura
                devoluciones_previas = Devolucion.objects.filter(
                    id_venta=venta, 
                    id_producto=producto
                )
                
                total_devuelto_antes = sum(d.cantidad for d in devoluciones_previas)
                cantidad_comprada = detalle_venta.cantidad
                disponible_para_devolver = cantidad_comprada - total_devuelto_antes

                # 3. Validar que no intente devolver más de lo que posee en saldo
                if cantidad_devolver > disponible_para_devolver:
                    raise Exception(
                        f"No puedes devolver {cantidad_devolver} unidades. "
                        f"Compró {cantidad_comprada} y ya devolvió {total_devuelto_antes}. "
                        f"Máximo disponible: {disponible_para_devolver}."
                    )

                # 4. Crear el registro de devolución con la cantidad correspondiente
                devolucion = Devolucion.objects.create(
                    id_venta=venta,
                    id_producto=producto,
                    fecha=fecha_ingresada,
                    plazo=plazo,
                    condiciones=condiciones,
                    estado="Aceptada",
                    cantidad=cantidad_devolver
                )

                # 5. Actualizar Stock sumando la cantidad exacta devuelta
                inventario = Inventario.objects.get(id_producto=producto)
                inventario.stock_actual += cantidad_devolver
                inventario.save()

                # 6. Registrar movimiento de inventario con la cantidad real
                id_usuario = request.session.get("id_usuario")
                MovimientoInventario.objects.create(
                    id_producto=producto,
                    id_usuario_id=id_usuario,
                    tipo_movimiento="ENTRADA",
                    cantidad=cantidad_devolver,
                    referencia=f"Devolución #{devolucion.id_devolucion}",
                    fecha_movimiento=timezone.now(),
                    observaciones=condiciones
                )

                return redirect("devolucion:index")

        except Exception as e:
            return render(request, "devolucion/index.html", {
                "error": str(e),
                "devoluciones": devoluciones,
                "facturas": facturas,
                "today": timezone.now().date().isoformat(),
            })

    context = {
        "devoluciones": devoluciones,
        "facturas": facturas,
        "today": timezone.now().date().isoformat(),
    }
    return render(request, "devolucion/index.html", context)

# =========================================================================
# ⚙️ HELPERS / SINCRO DE PRODUCTOS
# =========================================================================

def obtener_productos(request, id_factura):
    """
    Devuelve en formato JSON los productos pertenecientes
    a la factura seleccionada, permitiendo devoluciones parciales sucesivas
    calculando correctamente el saldo disponible sobre la columna 'cantidad'.
    """
    productos = []
    try:
        detalles = (
            DetalleVenta.objects
            .filter(id_venta_id=id_factura)
            .select_related("id_producto")
        )

        for detalle in detalles:
            producto = detalle.id_producto
            
            # Buscamos cuántas unidades ya se han devuelto sumando el campo real de la BD 'cantidad'
            devoluciones_previas = Devolucion.objects.filter(
                id_venta_id=id_factura, 
                id_producto=producto
            )
            
            total_devueltos = sum(d.cantidad for d in devoluciones_previas)
            
            # Cantidad que resta por devolver
            disponible = detalle.cantidad - total_devueltos

            # El producto SOLO se listará si aún le quedan unidades disponibles para devolver
            if disponible > 0:
                productos.append({
                    "id": producto.id_producto,
                    "nombre": producto.nombre,
                    "max_cantidad": disponible,  # Envía el tope real al JS
                })
    except Exception as e:
        print(f"Error en obtener_productos: {str(e)}")
        pass

    return JsonResponse({"productos": productos})

# =========================================================================
# ⚙️ HELPERS / SINCRO DE PRODUCTOS
# =========================================================================

def obtener_productos(request, id_factura):
    """
    Devuelve en formato JSON los productos pertenecientes
    a la factura seleccionada, permitiendo devoluciones parciales sucesivas
    calculando correctamente el saldo disponible sobre la columna 'cantidad'.
    """
    productos = []
    try:
        detalles = (
            DetalleVenta.objects
            .filter(id_venta_id=id_factura)
            .select_related("id_producto")
        )

        for detalle in detalles:
            producto = detalle.id_producto
            
            devoluciones_previas = Devolucion.objects.filter(
                id_venta_id=id_factura, 
                id_producto=producto
            )
            
            total_devueltos = sum(d.cantidad for d in devoluciones_previas)
            disponible = detalle.cantidad - total_devueltos

            if disponible > 0:
                productos.append({
                    "id": producto.id_producto,
                    "nombre": producto.nombre,
                    "max_cantidad": disponible,
                })
    except Exception as e:
        print(f"Error en obtener_productos: {str(e)}")
        pass

    return JsonResponse({"productos": productos})


# =========================================================================
# 🏠 VISTA PRINCIPAL: REGISTRO Y VISTA EN NAVEGADOR DEL COMPROBANTE
# =========================================================================

def index(request):
    buscar = request.GET.get("buscar", "")

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
        devoluciones = devoluciones.filter(id_producto__nombre__icontains=buscar)

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
        cantidad_devolver = request.POST.get("cantidad")

        if not all([fecha, plazo, condiciones, id_producto, id_factura, cantidad_devolver]):
            return render(request, "devolucion/index.html", {
                "error": "Todos los campos son obligatorios, incluida la cantidad.",
                "devoluciones": devoluciones,
                "facturas": facturas,
                "today": timezone.now().date().isoformat(),
            })

        try:
            plazo = int(plazo)
            cantidad_devolver = int(cantidad_devolver)
        except ValueError:
            return render(request, "devolucion/index.html", {
                "error": "El plazo y la cantidad deben ser valores numéricos.",
                "devoluciones": devoluciones,
                "facturas": facturas,
                "today": timezone.now().date().isoformat(),
            })

        if plazo <= 0 or cantidad_devolver <= 0:
            return render(request, "devolucion/index.html", {
                "error": "El plazo y la cantidad deben ser mayores a 0.",
                "devoluciones": devoluciones,
                "facturas": facturas,
                "today": timezone.now().date().isoformat(),
            })

        try:
            fecha_ingresada = datetime.strptime(fecha, "%Y-%m-%d").date()
            if fecha_ingresada < timezone.now().date():
                raise ValueError()
        except ValueError:
            return render(request, "devolucion/index.html", {
                "error": "Fecha inválida o anterior al día actual.",
                "devoluciones": devoluciones,
                "facturas": facturas,
                "today": timezone.now().date().isoformat(),
            })

        try:
            with transaction.atomic():
                venta = Venta.objects.get(id_venta=id_factura)
                producto = Producto.objects.get(id_producto=id_producto)

                detalle_venta = DetalleVenta.objects.filter(
                    id_venta=venta, 
                    id_producto=producto
                ).first()

                if not detalle_venta:
                    raise Exception("El producto no pertenece a la factura seleccionada.")

                devoluciones_previas = Devolucion.objects.filter(
                    id_venta=venta, 
                    id_producto=producto
                )
                
                total_devuelto_antes = sum(d.cantidad for d in devoluciones_previas)
                cantidad_comprada = detalle_venta.cantidad
                disponible_para_devolver = cantidad_comprada - total_devuelto_antes

                if cantidad_devolver > disponible_para_devolver:
                    raise Exception(
                        f"No puedes devolver {cantidad_devolver} unidades. "
                        f"Compró {cantidad_comprada} y ya devolvió {total_devuelto_antes}. "
                        f"Máximo disponible: {disponible_para_devolver}."
                    )

                devolucion = Devolucion.objects.create(
                    id_venta=venta,
                    id_producto=producto,
                    fecha=fecha_ingresada,
                    plazo=plazo,
                    condiciones=condiciones,
                    estado="Aceptada",
                    cantidad=cantidad_devolver
                )

                inventario = Inventario.objects.get(id_producto=producto)
                inventario.stock_actual += cantidad_devolver
                inventario.save()

                id_usuario = request.session.get("id_usuario")
                MovimientoInventario.objects.create(
                    id_producto=producto,
                    id_usuario_id=id_usuario,
                    tipo_movimiento="ENTRADA",
                    cantidad=cantidad_devolver,
                    referencia=f"Devolución #{devolucion.id_devolucion}",
                    fecha_movimiento=timezone.now(),
                    observaciones=condiciones
                )

                # =========================================================================
                # Cambiado a 'inline' para que el navegador lo visualice en pantalla
                # =========================================================================
                response = HttpResponse(content_type='application/pdf')
                response['Content-Disposition'] = f'inline; filename="Comprobante_Devolucion_{devolucion.id_devolucion}.pdf"'

                pdf = canvas.Canvas(response, pagesize=A4)
                width, height = A4
                azul = colors.HexColor("#0B4EA2")
                logo = os.path.join(settings.BASE_DIR, "static", "assets", "Ferreteria.png")

                _dibujar_comprobante_individual_pdf(pdf, devolucion, venta, producto, width, height, azul, logo)
                pdf.showPage()
                pdf.save()

                # El respaldo en disco se mantiene exactamente igual (silencioso e independiente)
                try:
                    ruta_devoluciones = settings.SUBCARPETAS_FERRETERIA.get("Devoluciones")
                    if ruta_devoluciones:
                        nombre_archivo_local = f"Comprobante_Devolucion_{devolucion.id_devolucion}.pdf"
                        ruta_completa_archivo = os.path.join(ruta_devoluciones, nombre_archivo_local)
                        
                        pdf_local = canvas.Canvas(ruta_completa_archivo, pagesize=A4)
                        _dibujar_comprobante_individual_pdf(pdf_local, devolucion, venta, producto, width, height, azul, logo)
                        pdf_local.showPage()
                        pdf_local.save()
                        print(f"[RESPALDO FÍSICO] Comprobante individual guardado en: {ruta_completa_archivo}")
                except Exception as e:
                    print(f"[ALERTA RESPALDO] No se pudo guardar la copia en disco duro: {e}")

                return response

        except Exception as e:
            return render(request, "devolucion/index.html", {
                "error": str(e),
                "devoluciones": devoluciones,
                "facturas": facturas,
                "today": timezone.now().date().isoformat(),
            })

    context = {
        "devoluciones": devoluciones,
        "facturas": facturas,
        "today": timezone.now().date().isoformat(),
    }
    return render(request, "devolucion/index.html", context)


# =========================================================================
# 📊 REPORTE PDF DE DEVOLUCIONES GENERALES (VISTA EN NAVEGADOR)
# =========================================================================

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

    # Cambiado a 'inline' también para el reporte completo
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="Reporte_Devoluciones.pdf"'

    pdf = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    azul = colors.HexColor("#0B4EA2")
    logo = os.path.join(settings.BASE_DIR, "static", "assets", "Ferreteria.png")

    _dibujar_contenido_devoluciones_pdf(pdf, devoluciones, width, height, azul, logo)
    pdf.showPage()
    pdf.save()

    try:
        ruta_devoluciones = settings.SUBCARPETAS_FERRETERIA.get("Devoluciones")
        if ruta_devoluciones:
            fecha_hoy = timezone.now().strftime('%Y%m%d_%H%M%S')
            nombre_archivo_local = f"Reporte_Devoluciones_{fecha_hoy}.pdf"
            ruta_completa_archivo = os.path.join(ruta_devoluciones, nombre_archivo_local)
            
            pdf_local = canvas.Canvas(ruta_completa_archivo, pagesize=A4)
            _dibujar_contenido_devoluciones_pdf(pdf_local, devoluciones, width, height, azul, logo)
            pdf_local.showPage()
            pdf_local.save()
            print(f"[RESPALDO DEVOLUCIONES] Reporte guardado físicamente en: {ruta_completa_archivo}")
    except Exception as e:
        print(f"[ALERTA RESPALDO] No se pudo guardar la copia del reporte masivo en disco. Motivo: {e}")

    return response


# =========================================================================
# 🎨 FUNCIONES AUXILIARES GRÁFICAS (REPORTLAB DIBUJO)
# =========================================================================

def _dibujar_comprobante_individual_pdf(pdf, devolucion, venta, producto, width, height, azul, logo):
    if os.path.exists(logo):
        pdf.drawImage(logo, 20, height - 180, width=290, height=180, preserveAspectRatio=True)

    pdf.setLineWidth(1)
    pdf.setStrokeColor(azul)
    pdf.rect(380, height - 90, 175, 30)
    pdf.rect(380, height - 120, 175, 30)

    pdf.setFont("Helvetica-Bold", 10)
    pdf.setFillColor(colors.black)
    pdf.drawString(385, height - 72, f"COMPROBANTE DEV N°: {devolucion.id_devolucion}")
    pdf.drawString(385, height - 102, f"FECHA DEV: {devolucion.fecha.strftime('%d/%m/%Y')}")

    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(40, height - 180, "DATOS DE LA EMPRESA")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, height - 200, "Dirección: Granada Diriomo, de la entrada principal")
    pdf.drawString(40, height - 214, " de Diriomo una cuadra al Norte a mano izquierda")
    pdf.drawString(40, height - 228, "Teléfono: +505 8765-4321")
    pdf.drawString(40, height - 242, "RUC/NIT: J-12345678-9")

    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(40, height - 280, "REFERENCIA DE VENTA ORIGINAL")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, height - 300, f"Código de Factura Afectada: #{venta.id_venta}")
    if hasattr(venta, 'id_cliente') and venta.id_cliente:
        pdf.drawString(40, height - 314, f"Cliente: {venta.id_cliente.nombre}")

    tabla_y = height - 360
    pdf.setFillColor(azul)
    pdf.rect(40, tabla_y, 515, 22, fill=True, stroke=False)
    
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(45, tabla_y + 6, "ID Prod")
    pdf.drawString(110, tabla_y + 6, "Descripción del Producto Retornado")
    pdf.drawRightString(540, tabla_y + 6, "Cant. Devuelta")

    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica", 10)
    y = tabla_y - 25
    
    pdf.setStrokeColor(colors.black)
    pdf.rect(40, y, 515, 25)
    
    pdf.drawString(45, y + 8, str(producto.id_producto))
    pdf.drawString(110, y + 8, producto.nombre[:50])
    pdf.drawRightString(540, y + 8, str(devolucion.cantidad))

    y_obs = y - 50
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(40, y_obs, "Motivo y Condiciones de Aceptación:")
    
    pdf.setFont("Helvetica", 10)
    pdf.setStrokeColor(colors.lightgrey)
    pdf.rect(40, y_obs - 60, 515, 50)
    
    observacion = devolucion.condiciones if devolucion.condiciones else "Sin observaciones."
    pdf.drawString(45, y_obs - 25, observacion[:90])
    if len(observacion) > 90:
        pdf.drawString(45, y_obs - 40, observacion[90:180])

    pdf.setFont("Helvetica-Oblique", 9)
    pdf.drawString(40, y_obs - 90, f"* Esta devolución generó una ENTRADA de {devolucion.cantidad} unidades al inventario.")
    pdf.drawString(40, y_obs - 105, f"* Plazo estipulado para seguimiento de reclamos: {devolucion.plazo} días.")

    pdf.setFillColor(azul)
    pdf.rect(0, 0, width, 35, fill=1)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(40, 12, "Ferretería Mi Casa - Control Interno")
    pdf.drawRightString(width - 40, 12, "COMPROBANTE DE DEVOLUCIÓN")


def _dibujar_contenido_devoluciones_pdf(pdf, devoluciones, width, height, azul, logo):
    if os.path.exists(logo):
        pdf.drawImage(logo, 20, height - 180, width=290, height=180, preserveAspectRatio=True)

    pdf.setLineWidth(1)
    pdf.setStrokeColor(azul)
    pdf.rect(400, height - 90, 150, 30)
    pdf.rect(400, height - 120, 150, 30)

    pdf.setFont("Helvetica-Bold", 11)
    pdf.setFillColor(colors.black)
    pdf.drawString(410, height - 72, "REPORTE DEVOLUCIONES")
    pdf.drawString(410, height - 102, f"FECHA: {timezone.now().strftime('%d/%m/%Y')}")

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, height - 180, "DATOS DE LA EMPRESA")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(40, height - 205, "Dirección: Granada Diriomo, de la entrada principal")
    pdf.drawString(40, height - 220, " de Diriomo una cuadra al Norte a mano izquierda")
    pdf.drawString(40, height - 245, "Teléfono: +505 8765-4321")
    pdf.drawString(40, height - 265, "RUC/NIT: J-12345678-9")
    pdf.drawString(40, height - 280, "Email: info@ferreteriamicasa.com")

    tabla_y = height - 340
    pdf.setFillColor(azul)
    pdf.rect(40, tabla_y, 510, 25, fill=1)

    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(45, tabla_y + 8, "FECHA")
    pdf.drawString(105, tabla_y + 8, "CLIENTE")
    pdf.drawString(195, tabla_y + 8, "PRODUCTO")
    pdf.drawString(285, tabla_y + 8, "CANT.")
    pdf.drawString(325, tabla_y + 8, "CONDICIONES")
    pdf.drawString(440, tabla_y + 8, "PLAZO")
    pdf.drawString(490, tabla_y + 8, "FACTURA")

    y = tabla_y - 25
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica", 8)

    for d in devoluciones:
        if y < 80:
            pdf.showPage()
            y = height - 50
            pdf.setFillColor(azul)
            pdf.rect(40, y, 510, 25, fill=1)
            pdf.setFillColor(colors.white)
            pdf.setFont("Helvetica-Bold", 9)
            pdf.drawString(45, y + 8, "FECHA")
            pdf.drawString(105, y + 8, "CLIENTE")
            pdf.drawString(195, y + 8, "PRODUCTO")
            pdf.drawString(285, y + 8, "CANT.")
            pdf.drawString(325, y + 8, "CONDICIONES")
            pdf.drawString(440, y + 8, "PLAZO")
            pdf.drawString(490, y + 8, "FACTURA")
            y -= 25
            pdf.setFillColor(colors.black)
            pdf.setFont("Helvetica", 8)

        pdf.setStrokeColor(colors.black)
        pdf.rect(40, y, 510, 25)
        pdf.drawString(45, y + 8, d.fecha.strftime("%d/%m/%Y"))
        pdf.drawString(105, y + 8, d.id_venta.id_cliente.nombre[:15])
        pdf.drawString(195, y + 8, d.id_producto.nombre[:15])
        pdf.drawString(285, y + 8, str(d.cantidad))
        pdf.drawString(325, y + 8, d.condiciones[:20] if d.condiciones else "N/A")
        pdf.drawString(440, y + 8, str(d.plazo))
        pdf.drawString(490, y + 8, str(d.id_venta.id_venta))
        y -= 25

    pdf.setFillColor(azul)
    pdf.rect(0, 0, width, 35, fill=1)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, 12, "www.ferreteriamicasa.NotenemosDominio.XD")
    pdf.drawRightString(width - 40, 12, "REPORTE DE DEVOLUCIONES")