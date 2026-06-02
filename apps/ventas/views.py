# Agrega estos imports al inicio del archivo
from reportlab.lib import colors
from django.conf import settings
import os
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import json

from apps.core.models import (
    Producto,
    Venta,
    DetalleVenta,
    Cliente,
    Usuario,
    Inventario,
    MovimientoInventario,
    FacturaCliente,
)

# ===============================
# ⚙️ CONFIG MONEDA
# ===============================
TIPO_CAMBIO = 36.5  # 1 USD = 36.5 C$


# ===============================
# 🏠 VISTA PRINCIPAL
# ===============================
def index(request):
    productos = Producto.objects.all()

    data = []
    for p in productos:
        inventario = Inventario.objects.filter(id_producto=p).first()
        stock = inventario.stock_actual if inventario else 0

        data.append({
            'id_producto': p.id_producto,
            'nombre': p.nombre,
            'precio': float(p.precio_venta or 0),
            'stock': stock,
            'categoria': p.id_categoria.nombre if p.id_categoria else '',
        })

    return render(request, 'ventas/index.html', {
        'productos': data,
        'tipo_cambio': TIPO_CAMBIO
    })


# ===============================
# 👤 OBTENER USUARIO ACTUAL
# ===============================
def _current_user(request):
    user_id = request.session.get("id_usuario")

    if user_id:
        usuario = Usuario.objects.filter(id_usuario=user_id).first()
        if usuario:
            return usuario

    return Usuario.objects.first()


# ===============================
# 🔍 BUSCAR CLIENTE
# ===============================
def buscar_cliente(request):
    q = request.GET.get('q', '').strip()

    if len(q) < 2:
        return JsonResponse([], safe=False)

    clientes = Cliente.objects.filter(nombre__icontains=q)[:10]

    return JsonResponse([
        {
            'id': c.id_cliente,
            'nombre': c.nombre
        }
        for c in clientes
    ], safe=False)


# ===============================
# 👤 CREAR CLIENTE
# ===============================
@csrf_exempt
def crear_cliente(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Método no permitido'})

    try:
        data = json.loads(request.body)

        nombre = data.get('nombre', '').strip()
        telefono = data.get('telefono', '').strip()
        direccion = data.get('direccion', '').strip()

        if not nombre:
            return JsonResponse({
                'status': 'error',
                'message': 'Nombre requerido'
            })

        # CORREGIDO: Eliminamos 'activo=True' ya que tu modelo solo maneja 'estado'
        cliente = Cliente.objects.create(
            nombre=nombre,
            telefono=telefono,
            direccion=direccion,
            estado='Activo',
            fecha_registro=timezone.now()
        )

        return JsonResponse({
            'status': 'success',
            'id': cliente.id_cliente,
            'nombre': cliente.nombre
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})
# ===============================
# 🧾 GENERAR NÚMERO DE FACTURA
# ===============================
def generar_numero_factura():
    ultima = FacturaCliente.objects.order_by('-id_factura').first()

    if ultima:
        siguiente = ultima.id_factura + 1
    else:
        siguiente = 1

    return f"FAC-{siguiente:06d}"


# ===============================
# 💳 GUARDAR VENTA + FACTURA
# ===============================
@csrf_exempt
@transaction.atomic
def guardar_venta(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Método inválido'})

    try:
        data = json.loads(request.body)

        carrito = data.get('carrito', [])
        total = data.get('total')
        moneda = data.get('moneda', 'NIO')
        cliente_id = data.get('cliente_id')
        envio = data.get('envio', False)    

        if not carrito or not isinstance(carrito, list):
            return JsonResponse({
                'status': 'error',
                'message': 'Carrito inválido'
            })

        if total is None:
            return JsonResponse({'status': 'error', 'message': 'Total inválido'})

        if not cliente_id:
            return JsonResponse({'status': 'error', 'message': 'Seleccione cliente'})

        cliente = Cliente.objects.filter(id_cliente=cliente_id).first()
        if not cliente:
            return JsonResponse({
                'status': 'error',
                'message': 'Cliente no existe'
            })

        usuario = _current_user(request)
        if not usuario:
            return JsonResponse({'status': 'error', 'message': 'No hay usuario disponible'})

        total_cordobas = float(total)
        if moneda == 'USD':
            total_cordobas *= TIPO_CAMBIO

        productos_map = {}

        for item in carrito:
            producto = Producto.objects.filter(
                id_producto=item['id']
            ).first()

            if not producto:
                return JsonResponse({
                    'status': 'error',
                    'message': f"Producto {item['id']} no existe"
                })

            inventario = Inventario.objects.filter(
                id_producto=producto
            ).first()

            if not inventario:
                return JsonResponse({
                    'status': 'error',
                    'message': f'{producto.nombre} sin inventario'
                })

            if inventario.stock_actual < item['cantidad']:
                return JsonResponse({
                    'status': 'error',
                    'message': f'Stock insuficiente: {producto.nombre}'
                })

            productos_map[item['id']] = (producto, inventario)

        # Crear venta
        venta = Venta.objects.create(
            id_cliente=cliente,
            id_usuario=usuario,
            fecha=timezone.now(),
            total=round(total_cordobas, 2)
        )

        subtotal_general = 0

        # Guardar detalle y actualizar inventario
        for item in carrito:
            producto, inventario = productos_map[item['id']]

            precio = float(item['precio'])
            if moneda == 'USD':
                precio *= TIPO_CAMBIO

            cantidad = int(item['cantidad'])
            subtotal = precio * cantidad
            subtotal_general += subtotal

            # DETALLE
            DetalleVenta.objects.create(
                id_venta=venta,
                id_producto=producto,
                cantidad=cantidad,
                precio_unitario=round(precio, 2),
                subtotal=round(subtotal, 2)
            )

            inventario.stock_actual -= cantidad
            inventario.fecha_actualizacion = timezone.now()
            inventario.save()

            MovimientoInventario.objects.create(
                id_producto=producto,
                id_usuario=usuario,
                tipo_movimiento='salida',
                cantidad=cantidad,
                referencia=f'Venta #{venta.id_venta}',
                fecha_movimiento=timezone.now(),
                observaciones=f'Salida por venta al cliente {cliente.nombre}'
            )

                # Calcular IVA ANTES de convertir moneda
        subtotal_sin_iva_original = round(subtotal_general / 1.15, 2)
        impuesto_original = round(subtotal_general - subtotal_sin_iva_original, 2)

        # Convertir a córdobas si es necesario
        if moneda == 'USD':
            subtotal_sin_iva = round(subtotal_sin_iva_original * TIPO_CAMBIO, 2)
            impuesto = round(impuesto_original * TIPO_CAMBIO, 2)
            total_final = round(subtotal_general * TIPO_CAMBIO, 2)
        else:
            subtotal_sin_iva = subtotal_sin_iva_original
            impuesto = impuesto_original
            total_final = round(subtotal_general, 2)

        # Crear factura
        factura = FacturaCliente.objects.create(
            id_venta=venta,
            numero_factura=generar_numero_factura(),
            tipo_comprobante='Factura',
            fecha_emision=timezone.now().date(),
            subtotal=subtotal_sin_iva,
            impuesto=impuesto,
            total=total_final,
            estado='Emitida'
        )

        return JsonResponse({
            'status': 'success',
            'message': 'Venta guardada correctamente',
            'venta_id': venta.id_venta,
            'factura_id': factura.id_factura,
            'numero_factura': factura.numero_factura,
            'pdf_url': f'/ventas/factura/{factura.id_factura}/pdf/'
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        })


# 📄 GENERAR FACTURA PDF
def generar_factura_pdf(request, factura_id):

    factura = get_object_or_404(
        FacturaCliente.objects.select_related(
            'id_venta__id_cliente'
        ),
        id_factura=factura_id
    )

    venta = factura.id_venta
    cliente = venta.id_cliente

    detalles = DetalleVenta.objects.filter(
        id_venta=venta
    ).select_related('id_producto')

    response = HttpResponse(content_type='application/pdf')

    response['Content-Disposition'] = (
        f'inline; filename="Factura_{factura.numero_factura}.pdf"'
    )

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
    # FACTURA Y FECHA
    # ==================================
    pdf.setLineWidth(1)

    pdf.rect(400, height - 90, 150, 30)
    pdf.rect(400, height - 120, 150, 30)

    pdf.setFont("Helvetica-Bold", 11)

    pdf.drawString(
        410,
        height - 72,
        f"FACTURA N°: {factura.numero_factura}"
    )

    pdf.drawString(
        410,
        height - 102,
        f"FECHA: {factura.fecha_emision.strftime('%d/%m/%Y')}"
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
    pdf.drawString(40, height - 280, "Email: admin.ferreteria@gmail.com")

    # ==================================
    # DATOS CLIENTE
    # ==================================
    pdf.setFont("Helvetica-Bold", 14)

    pdf.drawString(
        370,
        height - 180,
        "DATOS DEL CLIENTE"
    )

    pdf.setFont("Helvetica", 11)

    pdf.drawString(
        370,
        height - 205,
        f"Nombre: {cliente.nombre}"
    )

    pdf.drawString(
        370,
        height - 225,
        f"Dirección: {cliente.direccion or ''}"
    )

    pdf.drawString(
        370,
        height - 245,
        f"Teléfono: {cliente.telefono or ''}"
    )

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

    pdf.setFont("Helvetica-Bold", 10)

    pdf.drawString(50, tabla_y + 8, "CANTIDAD")
    pdf.drawString(130, tabla_y + 8, "DESCRIPCIÓN")
    pdf.drawString(360, tabla_y + 8, "PRECIO UNIT.")
    pdf.drawString(470, tabla_y + 8, "TOTAL")

    # ==================================
    # DETALLES
    # ==================================
    y = tabla_y - 25

    pdf.setFillColor(colors.black)

    for detalle in detalles:

        pdf.rect(40, y, 510, 25)

        pdf.drawString(
            55,
            y + 8,
            str(detalle.cantidad)
        )

        pdf.drawString(
            130,
            y + 8,
            detalle.id_producto.nombre[:40]
        )

        pdf.drawString(
            365,
            y + 8,
            f"C$ {detalle.precio_unitario:.2f}"
        )

        pdf.drawString(
            470,
            y + 8,
            f"C$ {detalle.subtotal:.2f}"
        )

        y -= 25

    # ==================================
    # MODO DE PAGO
    # ==================================
    box_y = y - 20

    pdf.setFillColor(azul)

    pdf.rect(40, box_y, 170, 25, fill=1)

    pdf.setFillColor(colors.white)

    pdf.setFont("Helvetica-Bold", 11)

    pdf.drawString(
        75,
        box_y + 8,
        "MODO DE PAGO"
    )

    pdf.setFillColor(colors.black)

    pdf.rect(40, box_y - 120, 170, 120)

    pdf.drawString(50, box_y - 20, "☐ Contado")

    # ==================================
    # NOTAS
    # ==================================
    pdf.setFillColor(colors.black)

    pdf.rect(
        230,
        box_y - 120,
        150,
        145
    )

    pdf.drawString(
        240,
        box_y + 8,
        "NOTAS"
    )

    # ==================================
    # RESUMEN
    # ==================================
    pdf.setFillColor(azul)

    pdf.rect(
        400,
        box_y,
        150,
        25,
        fill=1
    )

    pdf.setFillColor(colors.white)

    pdf.setFont(
        "Helvetica-Bold",
        11
    )

    pdf.drawString(
        420,
        box_y + 8,
        "RESUMEN"
    )

    pdf.setFillColor(colors.black)

    pdf.rect(400, box_y - 25, 150, 25)
    pdf.rect(400, box_y - 50, 150, 25)
    pdf.rect(400, box_y - 75, 150, 25)

    pdf.drawString(
        410,
        box_y - 17,
        f"SUBTOTAL: C$ {factura.subtotal:.2f}"
    )

    pdf.drawString(
        410,
        box_y - 42,
        f"IVA: C$ {factura.impuesto:.2f}"
    )

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawString(
        410,
        box_y - 67,
        f"TOTAL: C$ {factura.total:.2f}"
    )

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
        "GRACIAS POR SU COMPRA"
    )

    pdf.save()

    return response