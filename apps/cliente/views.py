from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from apps.core.models import Cliente


# ==========================================
# INDEX CLIENTES
# ==========================================
def index(request):

    # ==========================================
    # CLIENTES
    # ==========================================
    clientes = Cliente.objects.all().order_by("-id_cliente")

    total_clientes = clientes.count()

    clientes_activos = 0
    clientes_inactivos = 0
    clientes_nuevos_mes = 0
    clientes_con_compras = 0

    hoy = timezone.now()

    # ==========================================
    # VENTAS POR DÍA
    # ==========================================
    ventas_por_dia = [0, 0, 0, 0, 0, 0, 0]

    # ==========================================
    # RECORRER CLIENTES
    # ==========================================
    for cliente in clientes:

        total_compras = 0

        # ==========================================
        # VENTAS DEL CLIENTE
        # ==========================================
        if hasattr(cliente, "venta_set"):
            ventas = cliente.venta_set.all()
        else:
            ventas = []

        # ==========================================
        # LÓGICA DE ESTADO CONTROLADO POR BD (CORREGIDO)
        # ==========================================
        # Leemos el campo de texto 'estado' y removemos espacios en blanco que genera SQL Server
        estado_real = cliente.estado.strip() if getattr(cliente, "estado", None) else "Activo"

        if estado_real == "Activo":
            clientes_activos += 1
            cliente.estado = "Activo"  # Forzamos limpio para el HTML
        else:
            clientes_inactivos += 1
            cliente.estado = "Inactivo"  # Forzamos limpio para el HTML

        # ==========================================
        # CLIENTES NUEVOS DEL MES
        # ==========================================
        fecha_registro = getattr(cliente, "fecha_registro", None)

        if fecha_registro:

            if (
                fecha_registro.month == hoy.month
                and fecha_registro.year == hoy.year
            ):
                clientes_nuevos_mes += 1

        # ==========================================
        # TOTAL COMPRAS
        # ==========================================
        for venta in ventas:

            total = getattr(venta, "total", 0) or 0
            fecha = getattr(venta, "fecha", None)

            total_compras += float(total)

            # ==========================================
            # VENTAS POR DÍA
            # ==========================================
            if fecha:

                dia = fecha.weekday()

                ventas_por_dia[dia] += float(total)

        # ==========================================
        # GUARDAR TOTAL TEMPORAL
        # ==========================================
        cliente.total_compras = total_compras

        # ==========================================
        # CLIENTES CON COMPRAS
        # ==========================================
        if total_compras > 0:
            clientes_con_compras += 1

    # ==========================================
    # TOP CLIENTES
    # ==========================================
    top_clientes = sorted(
        clientes,
        key=lambda c: c.total_compras,
        reverse=True
    )[:5]

    # ==========================================
    # ACTIVIDAD RECIENTE
    # ==========================================
    clientes_actividad = sorted(
        [c for c in clientes if c.fecha_registro],
        key=lambda c: c.fecha_registro,
        reverse=True
    )[:3]

    # ==========================================
    # ESTADO CLIENTES
    # ==========================================
    estado_clientes = {
        "Activos": clientes_activos,
        "Inactivos": clientes_inactivos,
    }

    clientes_activos_lista = [
        c for c in clientes
        if (getattr(c, "estado", "") or "").strip() == "Activo"
    ]
    clientes_inactivos_lista = [
        c for c in clientes
        if (getattr(c, "estado", "") or "").strip() == "Inactivo"
    ]

    # ==========================================
    # CONTEXTO
    # ==========================================
    context = {
        "clientes": clientes,
        "clientes_activos_lista": clientes_activos_lista,
        "clientes_inactivos_lista": clientes_inactivos_lista,

        "total_clientes": total_clientes,
        "clientes_activos": clientes_activos,
        "clientes_inactivos": clientes_inactivos,
        "clientes_nuevos_mes": clientes_nuevos_mes,
        "clientes_con_compras": clientes_con_compras,

        "top_clientes": top_clientes,
        "clientes_actividad": clientes_actividad,

        "ventas_por_dia": ventas_por_dia,
        "estado_clientes": estado_clientes,
    }

    return render(
        request,
        "cliente/index.html",
        context
    )


# ==========================================
# EDITAR CLIENTE
# ==========================================
def editar_cliente(request, id):

    cliente = get_object_or_404(
        Cliente,
        id_cliente=id
    )

    if request.method == "POST":

        cliente.nombre = request.POST.get(
            "nombre",
            ""
        ).strip()

        cliente.telefono = request.POST.get(
            "telefono",
            ""
        ).strip()

        cliente.direccion = request.POST.get(
            "direccion",
            ""
        ).strip()

        cliente.save()

    return redirect("cliente:index")


# ==========================================
# ELIMINAR CLIENTE
# ==========================================
def eliminar_cliente(request, id):

    cliente = get_object_or_404(
        Cliente,
        id_cliente=id
    )

    if request.method == "POST":

        cliente.delete()

    return redirect("cliente:index")


# ==========================================
# CAMBIAR ESTADO CLIENTE (ACTIVAR / DESACTIVAR)
# ==========================================
def cambiar_estado_cliente(request, id):
    cliente = get_object_or_404(Cliente, id_cliente=id)
    
    # Evaluamos el campo 'estado' aplicando .strip() por los espacios en blanco de SQL Server
    if hasattr(cliente, 'estado') and cliente.estado:
        if cliente.estado.strip() == 'Activo':
            cliente.estado = 'Inactivo'
        else:
            cliente.estado = 'Activo'
            
    # Por seguridad, si tu modelo posee el campo booleano 'activo', lo invertimos también
    if hasattr(cliente, 'activo'):
        cliente.activo = not cliente.activo

    cliente.save()
    return redirect("cliente:index")