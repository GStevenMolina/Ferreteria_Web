from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.utils import timezone
import json

from apps.core.models import (
    Producto, Venta, DetalleVenta,
    Cliente, Usuario, Inventario, MovimientoInventario
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
# 👤 OBTENER USUARIO
# ===============================
def _current_user(request):
    user_id = request.session.get("id_usuario")
    if user_id:
        return Usuario.objects.filter(id_usuario=user_id).first()

    # fallback seguro
    return Usuario.objects.first()


# ===============================
# 🔍 BUSCAR CLIENTE
# ===============================
def buscar_cliente(request):
    q = request.GET.get('q', '')

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

        if not data.get('nombre'):
            return JsonResponse({'status': 'error', 'message': 'Nombre requerido'})

        cliente = Cliente.objects.create(
            nombre=data.get('nombre'),
            telefono=data.get('telefono'),
            direccion=data.get('direccion'),
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
# 💳 GUARDAR VENTA + INVENTARIO
# ===============================
@csrf_exempt
@transaction.atomic
def guardar_venta(request):

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Método inválido'})

    try:
        data = json.loads(request.body)

        carrito = data.get('carrito')
        total = data.get('total')
        moneda = data.get('moneda', 'NIO')
        cliente_id = data.get('cliente_id')

        # ===============================
        # VALIDACIONES
        # ===============================
        if not carrito or not isinstance(carrito, list):
            return JsonResponse({'status': 'error', 'message': 'Carrito inválido'})

        if total is None:
            return JsonResponse({'status': 'error', 'message': 'Total inválido'})

        if not cliente_id:
            return JsonResponse({'status': 'error', 'message': 'Seleccione cliente'})

        cliente = Cliente.objects.filter(id_cliente=cliente_id).first()
        if not cliente:
            return JsonResponse({'status': 'error', 'message': 'Cliente no existe'})

        usuario = _current_user(request)
        if not usuario:
            return JsonResponse({'status': 'error', 'message': 'No hay usuario disponible'})

        # ===============================
        # CONVERTIR TOTAL A CÓRDOBAS
        # ===============================
        total_cordobas = float(total)
        if moneda == "USD":
            total_cordobas *= TIPO_CAMBIO

        # ===============================
        # VALIDAR STOCK
        # ===============================
        productos_map = {}

        for item in carrito:
            producto = Producto.objects.get(id_producto=item['id'])
            inventario = Inventario.objects.filter(id_producto=producto).first()

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

        # ===============================
        # CREAR VENTA
        # ===============================
        venta = Venta.objects.create(
            id_cliente=cliente,
            id_usuario=usuario,
            fecha=timezone.now(),
            total=total_cordobas
        )

        # ===============================
        # DETALLE + STOCK + MOVIMIENTO
        # ===============================
        for item in carrito:
            producto, inventario = productos_map[item['id']]

            precio = float(item['precio'])

            if moneda == "USD":
                precio *= TIPO_CAMBIO

            subtotal = precio * item['cantidad']

            # DETALLE
            DetalleVenta.objects.create(
                id_venta=venta,
                id_producto=producto,
                cantidad=item['cantidad'],
                precio_unitario=precio,
                subtotal=subtotal
            )

            # ACTUALIZAR STOCK
            inventario.stock_actual -= item['cantidad']
            inventario.save()

            # 🔥 MOVIMIENTO INVENTARIO (CLAVE)
            MovimientoInventario.objects.create(
                id_producto=producto,
                id_usuario=usuario,
                tipo_movimiento="salida",  # 🔥 IMPORTANTE
                cantidad=item['cantidad'],
                referencia=f"Venta #{venta.id_venta}",
                fecha_movimiento=timezone.now(),
                observaciones=f"Salida)"
            )

        return JsonResponse({
            'status': 'success',
            'venta_id': venta.id_venta
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        })