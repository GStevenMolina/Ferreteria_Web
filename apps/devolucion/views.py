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
    ProductoDanado,  # <--- NUEVO: Importamos tu modelo de productos dañados
)

# =========================================================================
# ⚙️ HELPERS / SINCRO DE PRODUCTOS
# =========================================================================

def obtener_productos(request, id_factura):
    """
    Devuelve en formato JSON los productos pertenecientes
    a la factura seleccionada, permitiendo devoluciones parciales sucesivas.
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

    return JsonResponse({"productos": productos})


# =========================================================================
# 🏠 VISTA PRINCIPAL: REGISTRO Y VISTA MULTI-PRODUCTO
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
        id_factura = request.POST.get("id_factura")
        
        # ---> SOPORTE MULTI-PRODUCTO: Recibimos listas desde el HTML
        productos_ids = request.POST.getlist("id_producto")
        cantidades_devolver = request.POST.getlist("cantidad")
        # Lista de 'true' o 'false' para saber cuáles vienen defectuosos de fábrica/cliente
        estados_defectuosos = request.POST.getlist("es_defectuoso") 

        if not all([fecha, plazo, condiciones, id_factura, productos_ids, cantidades_devolver]):
            return render(request, "devolucion/index.html", {
                "error": "Todos los campos son obligatorios y debes seleccionar al menos un producto.",
                "devoluciones": devoluciones,
                "facturas": facturas,
                "today": timezone.now().date().isoformat(),
            })

        try:
            plazo = int(plazo)
            fecha_ingresada = datetime.strptime(fecha, "%Y-%m-%d").date()
            if fecha_ingresada < timezone.now().date():
                raise ValueError()
        except ValueError:
            return render(request, "devolucion/index.html", {
                "error": "Plazo inválido o fecha anterior al día actual.",
                "devoluciones": devoluciones,
                "facturas": facturas,
                "today": timezone.now().date().isoformat(),
            })

        try:
            devoluciones_creadas = []
            id_usuario = request.session.get("id_usuario")

            with transaction.atomic():
                venta = Venta.objects.get(id_venta=id_factura)

                # Iteramos sobre todos los productos seleccionados en la devolución
                for idx, prod_id in enumerate(productos_ids):
                    cantidad_dev = int(cantidades_devolver[idx])
                    if cantidad_dev <= 0:
                        continue

                    producto = Producto.objects.get(id_producto=prod_id)

                    # 1. Validar existencias originales en la venta
                    detalle_venta = DetalleVenta.objects.filter(id_venta=venta, id_producto=producto).first()
                    if not detalle_venta:
                        raise Exception(f"El producto {producto.nombre} no pertenece a esta factura.")

                    devoluciones_previas = Devolucion.objects.filter(id_venta=venta, id_producto=producto)
                    total_devuelto_antes = sum(d.cantidad for d in devoluciones_previas)
                    disponible_para_devolver = detalle_venta.cantidad - total_devuelto_antes

                    if cantidad_dev > disponible_para_devolver:
                        raise Exception(f"Cantidad excedida para {producto.nombre}. Máximo disponible: {disponible_para_devolver}")

                    # 2. Crear Registro de Devolución individual en la BD
                    devolucion = Devolucion.objects.create(
                        id_venta=venta,
                        id_producto=producto,
                        fecha=fecha_ingresada,
                        plazo=plazo,
                        condiciones=condiciones,
                        estado="Aceptada",
                        cantidad=cantidad_dev
                    )
                    devoluciones_creadas.append(devolucion)

                    # 3. Evaluar si el producto está defectuoso/dañado
                    # Nota: Asegúrate de enviar 'true' o 'false' desde cada fila de tu frontend
                    es_defectuoso = False
                    if idx < len(estados_defectuosos):
                        es_defectuoso = (estados_defectuosos[idx] == "true" or estados_defectuosos[idx] == "si")

                    inventario = Inventario.objects.get(id_producto=producto)

                    if es_defectuoso:
                        # --- FLUJO PRODUCTO DAÑADO ---
                        # Ingrese al inventario por la devolución teórica
                        inventario.stock_actual += cantidad_dev
                        # Sale inmediatamente por estar roto/defectuoso
                        inventario.stock_actual -= cantidad_dev
                        inventario.save()

                        # Registro en la tabla de productos dañados en PENDIENTE
                        ProductoDanado.objects.create(
                            id_devolucion=devolucion,
                            id_producto=producto,
                            id_usuario_id=id_usuario,
                            cantidad=cantidad_dev,
                            motivo_dano=condiciones,
                            estado_proceso='PENDIENTE',
                            observaciones=f"Automático - Ref Dev #{devolucion.id_devolucion}"
                        )

                        # Doble movimiento en historial para transparencia de auditoría
                        MovimientoInventario.objects.create(
                            id_producto=producto, id_usuario_id=id_usuario,
                            tipo_movimiento="ENTRADA", cantidad=cantidad_dev,
                            referencia=f"Devolución #{devolucion.id_devolucion}",
                            fecha_movimiento=timezone.now(), observaciones=condiciones
                        )
                        MovimientoInventario.objects.create(
                            id_producto=producto, id_usuario_id=id_usuario,
                            tipo_movimiento="SALIDA POR DAÑO", cantidad=cantidad_dev,
                            referencia=f"Baja por Daño #{devolucion.id_devolucion}",
                            fecha_movimiento=timezone.now(), observaciones=f"Descarte: {condiciones}"
                        )
                    else:
                        # --- FLUJO NORMAL (Reingresa limpio al Stock) ---
                        inventario.stock_actual += cantidad_dev
                        inventario.save()

                        # Movimiento único de Entrada
                        MovimientoInventario.objects.create(
                            id_producto=producto, id_usuario_id=id_usuario,
                            tipo_movimiento="ENTRADA", cantidad=cantidad_dev,
                            referencia=f"Devolución #{devolucion.id_devolucion}",
                            fecha_movimiento=timezone.now(), observaciones=condiciones
                        )

                # =========================================================================
                # GENERACIÓN DEL COMPROBANTE UNIFICADO (PDF MULTI-PRODUCTO)
                # =========================================================================
                response = HttpResponse(content_type='application/pdf')
                primera_dev = devoluciones_creadas[0]
                response['Content-Disposition'] = f'inline; filename="Comprobante_Devolucion_{primera_dev.id_devolucion}.pdf"'

                pdf = canvas.Canvas(response, pagesize=A4)
                width, height = A4
                azul = colors.HexColor("#0B4EA2")
                logo = os.path.join(settings.BASE_DIR, "static", "assets", "Ferreteria.png")

                _dibujar_comprobante_individual_pdf(pdf, devoluciones_creadas, venta, width, height, azul, logo)
                pdf.showPage()
                pdf.save()

                # Respaldo físico en disco duro
                try:
                    ruta_devoluciones = settings.SUBCARPETAS_FERRETERIA.get("Devoluciones")
                    if ruta_devoluciones:
                        nombre_archivo_local = f"Comprobante_Devolucion_{primera_dev.id_devolucion}.pdf"
                        ruta_completa_archivo = os.path.join(ruta_devoluciones, nombre_archivo_local)
                        
                        pdf_local = canvas.Canvas(ruta_completa_archivo, pagesize=A4)
                        _dibujar_comprobante_individual_pdf(pdf_local, devoluciones_creadas, venta, width, height, azul, logo)
                        pdf_local.showPage()
                        pdf_local.save()
                except Exception as e:
                    print(f"[ALERTA RESPALDO] Copia local fallida: {e}")

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
# 📊 REPORTE GENERAL (Mantiene su flujo masivo original)
# =========================================================================
def reporte_devoluciones_pdf(request):
    devoluciones = Devolucion.objects.select_related("id_producto", "id_venta", "id_venta__id_cliente").order_by("-id_devolucion")
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="Reporte_Devoluciones.pdf"'
    pdf = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    azul = colors.HexColor("#0B4EA2")
    logo = os.path.join(settings.BASE_DIR, "static", "assets", "Ferreteria.png")
    _dibujar_contenido_devoluciones_pdf(pdf, devoluciones, width, height, azul, logo)
    pdf.showPage()
    pdf.save()
    return response


# =========================================================================
# 🎨 FUNCIONES AUXILIARES GRÁFICAS (MUESTRA PRECIOS Y REEMBOLSOS)
# =========================================================================

def _dibujar_comprobante_individual_pdf(pdf, devoluciones_creadas, venta, width, height, azul, logo):
    primera_dev = devoluciones_creadas[0]
    
    if os.path.exists(logo):
        pdf.drawImage(logo, 20, height - 140, width=220, height=140, preserveAspectRatio=True)

    pdf.setLineWidth(1)
    pdf.setStrokeColor(azul)
    pdf.rect(360, height - 90, 195, 30)
    pdf.rect(360, height - 120, 195, 30)

    pdf.setFont("Helvetica-Bold", 10)
    pdf.setFillColor(colors.black)
    pdf.drawString(365, height - 72, f"COMPROBANTE GRUPO DEV N°: {primera_dev.id_devolucion}")
    pdf.drawString(365, height - 102, f"FECHA DEV: {primera_dev.fecha.strftime('%d/%m/%Y')}")

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, height - 160, "DATOS DE LA EMPRESA")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(40, height - 175, "Dirección: Granada Diriomo, de la entrada principal de Diriomo 1c al Norte")
    pdf.drawString(40, height - 190, "Teléfono: +505 8765-4321  |  RUC: J-12345678-9")

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, height - 220, "REFERENCIA DE VENTA ORIGINAL")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, height - 235, f"Código de Factura Afectada: #{venta.id_venta}")
    if hasattr(venta, 'id_cliente') and venta.id_cliente:
        pdf.drawString(40, height - 250, f"Cliente: {venta.id_cliente.nombre}")

    # --- ENCABEZADOS DE LA TABLA ---
    tabla_y = height - 290
    pdf.setFillColor(azul)
    pdf.rect(40, tabla_y, 515, 22, fill=True, stroke=False)
    
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(45, tabla_y + 6, "ID")
    pdf.drawString(85, tabla_y + 6, "Descripción del Producto Retornado")
    pdf.drawRightString(370, tabla_y + 6, "Precio Unit.")
    pdf.drawRightString(440, tabla_y + 6, "Cant.")
    pdf.drawRightString(540, tabla_y + 6, "Total Reembolso")

    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica", 9)
    y = tabla_y - 22
    
    gran_total_dinero = 0

    # --- FILAS DINÁMICAS (Para soportar múltiples artículos en la misma hoja) ---
    for d in devoluciones_creadas:
        producto = d.id_producto
        
        # Consultamos el precio real al que se le vendió en su momento
        detalle_v = DetalleVenta.objects.filter(id_venta=venta, id_producto=producto).first()
        precio_original = detalle_v.precio_unitario if detalle_v else producto.precio_venta
        subtotal_reembolso = precio_original * d.cantidad
        gran_total_dinero += subtotal_reembolso

        pdf.setStrokeColor(colors.lightgrey)
        pdf.rect(40, y, 515, 22)
        
        pdf.drawString(45, y + 6, str(producto.id_producto))
        pdf.drawString(85, y + 6, producto.nombre[:40])
        pdf.drawRightString(370, y + 6, f"C$ {precio_original:,.2f}")
        pdf.drawRightString(440, y + 6, str(d.cantidad))
        pdf.drawRightString(540, y + 6, f"C$ {subtotal_reembolso:,.2f}")
        
        y -= 22

    # --- CUADRO DE TOTALES (REEMBOLSO EN EFECTIVO / CRÉDITO) ---
    y -= 10
    pdf.setStrokeColor(azul)
    pdf.setFillColor(colors.HexColor("#F0F4F8"))
    pdf.rect(340, y - 25, 215, 25, fill=True, stroke=True)
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(345, y - 18, "TOTAL A REEMBOLSAR:")
    pdf.drawRightString(540, y - 18, f"C$ {gran_total_dinero:,.2f}")

    # Sección de observaciones estructurada de forma relativa a la tabla
    y_obs = y - 60
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(40, y_obs, "Motivo y Condiciones de Aceptación:")
    
    pdf.setFont("Helvetica", 10)
    pdf.setStrokeColor(colors.lightgrey)
    pdf.rect(40, y_obs - 45, 515, 35)
    
    observacion = primera_dev.condiciones if primera_dev.condiciones else "Sin observaciones."
    pdf.drawString(45, y_obs - 25, observacion[:90])

    pdf.setFont("Helvetica-Oblique", 9)
    pdf.drawString(40, y_obs - 65, f"* Plazo estipulado para seguimiento de reclamos: {primera_dev.plazo} días.")
    pdf.drawString(40, y_obs - 78, "* El dinero equivalente ha sido calculado en base a los precios de venta originales.")

    # Footer fijo
    pdf.setFillColor(azul)
    pdf.rect(0, 0, width, 35, fill=1)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(40, 12, "Ferretería Mi Casa - Control Interno")
    pdf.drawRightString(width - 40, 12, "COMPROBANTE DE REEMBOLSO / DEVOLUCIÓN")


def _dibujar_contenido_devoluciones_pdf(pdf, devoluciones, width, height, azul, logo):
    # (Se mantiene intacto tu reporte masivo original...)
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
    pdf.drawString(40, height - 205, "Dirección: Granada Diriomo")
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
            y -= 25
        pdf.setStrokeColor(colors.black)
        pdf.rect(40, y, 510, 25)
        pdf.drawString(45, y + 8, d.fecha.strftime("%d/%m/%Y"))
        pdf.drawString(105, y + 8, d.id_venta.id_cliente.nombre[:15] if d.id_venta.id_cliente else "Anónimo")
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
    pdf.drawString(40, 12, "www.ferreteriamicasa.com")
    pdf.drawRightString(width - 40, 12, "REPORTE DE DEVOLUCIONES")