from django import forms


UNIT_CHOICES = [
    ("unidad", "Unidad"),
    ("caja", "Caja"),
    ("metro", "Metro"),
    ("litro", "Litro"),
    ("kilogramo", "Kilogramo"),
    ("paquete", "Paquete"),
    ("rollo", "Rollo"),
]


MOVEMENT_CHOICES = [
    ("entrada", "Entrada (compra)"),
    ("salida", "Salida (venta)"),
    ("ajuste_entrada", "Ajuste +"),
    ("ajuste_salida", "Ajuste -"),
]


class ProductForm(forms.Form):
    product_id = forms.CharField(required=False, widget=forms.HiddenInput())
    codigo_producto = forms.CharField(required=False, disabled=True, label="Código de producto")
    nombre = forms.CharField(max_length=100)
    descripcion = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    categoria = forms.IntegerField()
    proveedor = forms.IntegerField(required=False)
    unidad_medida = forms.ChoiceField(choices=UNIT_CHOICES)
    precio_compra = forms.DecimalField(min_value=0.01, max_digits=18, decimal_places=2)
    precio_venta = forms.DecimalField(min_value=0.01, max_digits=18, decimal_places=2)
    stock_actual = forms.IntegerField(required=False, disabled=True)
    stock_minimo = forms.IntegerField(min_value=0)

    def __init__(self, *args, categories=None, providers=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].widget = forms.Select()
        self.fields["categoria"].choices = [(cat.id_categoria, cat.nombre) for cat in (categories or [])]
        self.fields["proveedor"].widget = forms.Select()
        self.fields["proveedor"].choices = [("", "Sin proveedor")] + [
            (prov.id_proveedor, prov.nombre) for prov in (providers or [])
        ]
        self.fields["codigo_producto"].widget.attrs.update({"readonly": "readonly"})
        self.fields["stock_actual"].widget.attrs.update({"readonly": "readonly"})

    def clean_nombre(self):
        value = (self.cleaned_data["nombre"] or "").strip()
        if not value:
            raise forms.ValidationError("El nombre es obligatorio.")
        return value

    def clean_precio_compra(self):
        value = self.cleaned_data["precio_compra"]
        if value <= 0:
            raise forms.ValidationError("El precio de compra debe ser mayor que cero.")
        return value

    def clean_precio_venta(self):
        value = self.cleaned_data["precio_venta"]
        if value <= 0:
            raise forms.ValidationError("El precio de venta debe ser mayor que cero.")
        return value

    def clean_stock_minimo(self):
        value = self.cleaned_data["stock_minimo"]
        if value < 0:
            raise forms.ValidationError("El stock mínimo no puede ser negativo.")
        return value


class MovementForm(forms.Form):
    producto = forms.CharField(max_length=200)
    tipo_movimiento = forms.ChoiceField(choices=MOVEMENT_CHOICES)
    cantidad = forms.IntegerField(min_value=1)
    observacion = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def clean_producto(self):
        value = (self.cleaned_data["producto"] or "").strip()
        if not value:
            raise forms.ValidationError("Selecciona un producto.")
        return value

    def clean_cantidad(self):
        value = self.cleaned_data["cantidad"]
        if value <= 0:
            raise forms.ValidationError("La cantidad debe ser mayor que cero.")
        return value