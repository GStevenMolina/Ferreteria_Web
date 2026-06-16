# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models

class Beneficiocliente(models.Model):
    id_beneficio = models.AutoField(primary_key=True)
    id_cliente = models.ForeignKey('Cliente', models.DO_NOTHING, db_column='id_cliente', blank=True, null=True)
    tipo = models.CharField(max_length=50, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    frecuencia = models.CharField(max_length=50, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    condicion = models.TextField(db_collation='Modern_Spanish_CI_AS', blank=True, null=True)  # This field type is a guess.
    restricciones = models.TextField(db_collation='Modern_Spanish_CI_AS', blank=True, null=True)  # This field type is a guess.
    porcentajedescuento = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'beneficiocliente'


class Categoria(models.Model):
    id_categoria = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100, db_collation='Modern_Spanish_CI_AS')
    descripcion = models.TextField(db_collation='Modern_Spanish_CI_AS', blank=True, null=True)  # This field type is a guess.
    fecha_creacion = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'categoria'


class Cliente(models.Model):
    id_cliente = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100, db_collation='Modern_Spanish_CI_AS')
    telefono = models.CharField(max_length=20, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    direccion = models.TextField(db_collation='Modern_Spanish_CI_AS', blank=True, null=True)  # This field type is a guess.
    fecha_registro = models.DateTimeField(blank=True, null=True)
    estado = models.CharField(max_length=10, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)  # <--- NUEVO

    class Meta:
        managed = False
        db_table = 'cliente'


class Compra(models.Model):
    id_compra = models.AutoField(primary_key=True)
    id_proveedor = models.ForeignKey('Proveedor', models.DO_NOTHING, db_column='id_proveedor', blank=True, null=True)
    id_usuario = models.ForeignKey('Usuario', models.DO_NOTHING, db_column='id_usuario', blank=True, null=True)
    fecha = models.DateTimeField(blank=True, null=True)
    total = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'compra'


class DetalleCompra(models.Model):
    id_detallecompra = models.AutoField(primary_key=True)
    id_compra = models.ForeignKey(Compra, models.DO_NOTHING, db_column='id_compra', blank=True, null=True)
    id_producto = models.ForeignKey('Producto', models.DO_NOTHING, db_column='id_producto', blank=True, null=True)
    cantidad = models.IntegerField(blank=True, null=True)
    precio_unitario = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'detalle_compra'


class DetalleVenta(models.Model):
    id_detalleventa = models.AutoField(primary_key=True)
    id_venta = models.ForeignKey('Venta', models.DO_NOTHING, db_column='id_venta', blank=True, null=True)
    id_producto = models.ForeignKey('Producto', models.DO_NOTHING, db_column='id_producto', blank=True, null=True)
    cantidad = models.IntegerField(blank=True, null=True)
    precio_unitario = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'detalle_venta'


class Devolucion(models.Model):
    id_devolucion = models.AutoField(primary_key=True)
    id_venta = models.ForeignKey('Venta', models.DO_NOTHING, db_column='id_venta', blank=True, null=True)
    id_producto = models.ForeignKey('Producto', models.DO_NOTHING, db_column='id_producto', blank=True, null=True)
    id_factura = models.ForeignKey('FacturaCliente', models.DO_NOTHING, db_column='id_factura', blank=True, null=True)
    fecha = models.DateTimeField(blank=True, null=True)
    cantidad = models.IntegerField(default=1)
    plazo = models.IntegerField(blank=True, null=True)
    condiciones = models.TextField(db_collation='Modern_Spanish_CI_AS', blank=True, null=True)  # This field type is a guess.
    restricciones = models.TextField(db_collation='Modern_Spanish_CI_AS', blank=True, null=True)  # This field type is a guess.
    estado = models.CharField(max_length=20, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'devolucion'


class FacturaCliente(models.Model):
    id_factura = models.AutoField(primary_key=True)
    id_venta = models.ForeignKey('Venta', models.DO_NOTHING, db_column='id_venta', blank=True, null=True)
    numero_factura = models.CharField(max_length=50, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    tipo_comprobante = models.CharField(max_length=50, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    fecha_emision = models.DateField(blank=True, null=True)
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)
    impuesto = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)
    total = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)
    estado = models.CharField(max_length=20, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'factura_cliente'


class FacturaProveedor(models.Model):
    id_factura_proveedor = models.AutoField(primary_key=True)
    id_compra = models.ForeignKey(Compra, models.DO_NOTHING, db_column='id_compra', blank=True, null=True)
    numero_factura = models.CharField(max_length=50, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    tipo_comprobante = models.CharField(max_length=50, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    fecha_emision = models.DateField(blank=True, null=True)
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)
    impuesto = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)
    total = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)
    estado = models.CharField(max_length=20, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'factura_proveedor'


class Inventario(models.Model):
    id_inventario = models.AutoField(primary_key=True)
    id_producto = models.ForeignKey('Producto', models.DO_NOTHING, db_column='id_producto', blank=True, null=True)
    stock_actual = models.IntegerField(blank=True, null=True)
    stock_minimo = models.IntegerField(blank=True, null=True)
    stock_maximo = models.IntegerField(blank=True, null=True)
    fecha_actualizacion = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'inventario'


class MovimientoInventario(models.Model):
    id_movimiento = models.AutoField(primary_key=True)
    id_producto = models.ForeignKey('Producto', models.DO_NOTHING, db_column='id_producto', blank=True, null=True)
    id_usuario = models.ForeignKey('Usuario', models.DO_NOTHING, db_column='id_usuario', blank=True, null=True)
    tipo_movimiento = models.CharField(max_length=50, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    cantidad = models.IntegerField(blank=True, null=True)
    referencia = models.CharField(max_length=100, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    fecha_movimiento = models.DateTimeField(blank=True, null=True)
    observaciones = models.TextField(db_collation='Modern_Spanish_CI_AS', blank=True, null=True)  # This field type is a guess.

    class Meta:
        managed = False
        db_table = 'movimiento_inventario'


class Producto(models.Model):
    id_producto = models.AutoField(primary_key=True)
    id_proveedor = models.ForeignKey('Proveedor', models.DO_NOTHING, db_column='id_proveedor', blank=True, null=True)
    id_categoria = models.ForeignKey(Categoria, models.DO_NOTHING, db_column='id_categoria', blank=True, null=True)
    nombre = models.CharField(max_length=100, db_collation='Modern_Spanish_CI_AS')
    descripcion = models.TextField(db_collation='Modern_Spanish_CI_AS', blank=True, null=True)  # This field type is a guess.
    precio_compra = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)
    precio_venta = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)
    unidad_medida = models.CharField(max_length=20, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    fecha_creacion = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'producto'


class Proveedor(models.Model):
    id_proveedor = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100, db_collation='Modern_Spanish_CI_AS')
    telefono = models.CharField(max_length=20, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    email = models.CharField(max_length=100, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    numero_contacto = models.CharField(max_length=100, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    direccion = models.TextField(db_collation='Modern_Spanish_CI_AS', blank=True, null=True)  # This field type is a guess.
    tipo_proveedor = models.CharField(max_length=50, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    fecha_registro = models.DateTimeField(blank=True, null=True)
    estado = models.CharField(max_length=10, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)  # <--- NUEVO
    

    class Meta:
        managed = False
        db_table = 'proveedor'


class Usuario(models.Model):
    id_usuario = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100, db_collation='Modern_Spanish_CI_AS')
    email = models.CharField(unique=True, max_length=100, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    password = models.CharField(max_length=255, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    rol = models.CharField(max_length=50, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    activo = models.BooleanField(blank=True, null=True)
    fecha_creacion = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'usuario'

class Auditoria(models.Model):
    usuario = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True,
        help_text="Usuario que intentó iniciar sesión, si existe"
    )
    email = models.CharField(max_length=100, help_text="Correo usado para el login")
    exito = models.BooleanField(help_text="¿El inicio de sesión fue exitoso?")
    fecha = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "auditoria"  # <--- Este nombre se usará en la base de datos
        managed = False  # <--- Permite que Django administre esta tabla

    def __str__(self):
        if self.usuario:
            return f"{self.fecha} - {self.usuario.nombre} - {'Éxito' if self.exito else 'Fallo'}"
        return f"{self.fecha} - {self.email} - {'Éxito' if self.exito else 'Fallo'}"
    
    from django.db import models

class AuditoriaEvento(models.Model):
    usuario = models.ForeignKey(
        'Usuario', on_delete=models.SET_NULL, null=True, blank=True,
        db_column='usuario_id', help_text="Usuario que realizó la acción"
    )
    email = models.CharField(max_length=100, help_text="Correo del usuario")
    evento = models.CharField(max_length=100, help_text="Tipo de evento/acción realizado")
    descripcion = models.TextField(null=True, blank=True, help_text="Detalle adicional")
    modulo = models.CharField(max_length=50, null=True, blank=True, help_text="Módulo relacionado")
    fecha = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "auditoria_evento"
        managed = False  # Porque la creas tú desde SQL… Django NO la modifica.

    def __str__(self):
        return f"{self.fecha} - {self.evento} - {self.email}"

class Venta(models.Model):
    id_venta = models.AutoField(primary_key=True)
    id_cliente = models.ForeignKey(Cliente, models.DO_NOTHING, db_column='id_cliente', blank=True, null=True)
    id_usuario = models.ForeignKey(Usuario, models.DO_NOTHING, db_column='id_usuario', blank=True, null=True)
    fecha = models.DateTimeField(blank=True, null=True)
    total = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'venta'
