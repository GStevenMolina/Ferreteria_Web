from django import forms


# Opciones de unidad de medida disponibles para los productos
UNIT_CHOICES = [
    ("unidad", "Unidad"),
    ("caja", "Caja"),
    ("metro", "Metro"),
    ("litro", "Litro"),
    ("kilogramo", "Kilogramo"),
    ("paquete", "Paquete"),
    ("rollo", "Rollo"),
]


# Tipos de movimiento de inventario soportados
MOVEMENT_CHOICES = [
    ("entrada", "Entrada (compra)"),
    ("salida", "Salida (venta)"),
    ("ajuste_entrada", "Ajuste +"),
    ("ajuste_salida", "Ajuste -"),
]


class ProductForm(forms.Form):
    """
    Formulario para crear y editar productos del inventario.
    Los campos 'codigo_producto' y 'stock_actual' son de solo lectura
    (se controlan desde el servidor, no pueden editarse por el usuario).
    Las opciones de categoría y proveedor se inyectan dinámicamente
    a través del constructor para que reflejen los datos actuales de la BD.
    """
    # Campo oculto que almacena el ID del producto al editar (vacío al crear)
    product_id = forms.CharField(required=False, widget=forms.HiddenInput())
    # Código autogenerado; se muestra pero no es editable
    codigo_producto = forms.CharField(required=False, disabled=True, label="Código de producto")
    nombre = forms.CharField(max_length=100)
    descripcion = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    # ID de la categoría seleccionada; las opciones se asignan en __init__
    categoria = forms.IntegerField()
    # ID del proveedor; opcional (puede quedar sin proveedor)
    proveedor = forms.IntegerField(required=False)
    unidad_medida = forms.ChoiceField(choices=UNIT_CHOICES)
    precio_compra = forms.DecimalField(min_value=0.01, max_digits=18, decimal_places=2)
    precio_venta = forms.DecimalField(min_value=0.01, max_digits=18, decimal_places=2)
    # Stock calculado por movimientos; solo lectura
    stock_actual = forms.IntegerField(required=False, disabled=True)
    stock_minimo = forms.IntegerField(min_value=0)

    def __init__(self, *args, categories=None, providers=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Rellenar el widget de categoría con las opciones de la BD
        self.fields["categoria"].widget = forms.Select()
        self.fields["categoria"].choices = [(cat.id_categoria, cat.nombre) for cat in (categories or [])]
        # Rellenar el widget de proveedor con las opciones de la BD, incluyendo "Sin proveedor"
        self.fields["proveedor"].widget = forms.Select()
        self.fields["proveedor"].choices = [("", "Sin proveedor")] + [
            (prov.id_proveedor, prov.nombre) for prov in (providers or [])
        ]
        # Marcar los campos de solo lectura con el atributo HTML readonly
        self.fields["codigo_producto"].widget.attrs.update({"readonly": "readonly"})
        self.fields["stock_actual"].widget.attrs.update({"readonly": "readonly"})

    def clean_nombre(self):
        """Validar que el nombre del producto no esté vacío."""
        value = (self.cleaned_data["nombre"] or "").strip()
        if not value:
            raise forms.ValidationError("El nombre es obligatorio.")
        return value

    def clean_precio_compra(self):
        """Validar que el precio de compra sea mayor que cero."""
        value = self.cleaned_data["precio_compra"]
        if value <= 0:
            raise forms.ValidationError("El precio de compra debe ser mayor que cero.")
        return value

    def clean_precio_venta(self):
        """Validar que el precio de venta sea mayor que cero."""
        value = self.cleaned_data["precio_venta"]
        if value <= 0:
            raise forms.ValidationError("El precio de venta debe ser mayor que cero.")
        return value

    def clean_stock_minimo(self):
        """Validar que el stock mínimo no sea negativo."""
        value = self.cleaned_data["stock_minimo"]
        if value < 0:
            raise forms.ValidationError("El stock mínimo no puede ser negativo.")
        return value


class MovementForm(forms.Form):
    """
    Formulario para registrar movimientos de inventario (entradas, salidas y ajustes).
    El campo 'producto' acepta el formato "id | nombre" generado por el datalist.
    """
    # Texto del producto seleccionado desde el datalist (formato "id | nombre")
    producto = forms.CharField(max_length=200)
    tipo_movimiento = forms.ChoiceField(choices=MOVEMENT_CHOICES)
    # Cantidad del movimiento; debe ser al menos 1
    cantidad = forms.IntegerField(min_value=1)
    observacion = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def clean_producto(self):
        """Validar que se haya indicado un producto para el movimiento."""
        value = (self.cleaned_data["producto"] or "").strip()
        if not value:
            raise forms.ValidationError("Selecciona un producto.")
        return value

    def clean_cantidad(self):
        """Validar que la cantidad sea mayor que cero."""
        value = self.cleaned_data["cantidad"]
        if value <= 0:
            raise forms.ValidationError("La cantidad debe ser mayor que cero.")
        return value