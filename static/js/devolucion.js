document.addEventListener("DOMContentLoaded", function () {

    // ==========================================================
    // BUSCADOR DE LA TABLA DE DEVOLUCIONES
    // ==========================================================
    const buscador = document.getElementById("buscador");

    if (buscador) {
        buscador.addEventListener("keyup", function () {
            const texto = this.value.toLowerCase();
            const filas = document.querySelectorAll("#tablaDevoluciones tbody tr");

            filas.forEach(function (fila) {
                const producto = fila.querySelector(".producto");
                if (!producto) return; // Ignorar fila vacía

                const nombreProducto = producto.textContent.toLowerCase();
                fila.style.display = nombreProducto.includes(texto) ? "" : "none";
            });
        });
    }

    // ==========================================================
    // SELECTS E INPUTS DE CONTROL DÍNÁMICO
    // ==========================================================
    const selectFactura = document.getElementById("id_factura");
    const selectProducto = document.getElementById("id_producto");
    const inputCantidad = document.getElementById("cantidad");
    const helperCantidad = document.getElementById("helper-cantidad");
    
    // Almacenará los productos de la factura activa con sus topes de cantidad
    let productosCache = []; 

    // ==========================================================
    // CARGAR PRODUCTOS SEGÚN FACTURA (SIN REFRESCAR)
    // ==========================================================
    if (selectFactura && selectProducto) {

        selectFactura.addEventListener("change", function () {
            const idFactura = this.value;

            // Resetear estados del select e input de cantidad
            selectProducto.innerHTML = '<option value="">Cargando productos...</option>';
            resetearInputCantidad();
            productosCache = [];

            const inputCliente = document.getElementById("cliente_factura");
            const contenedorCliente = document.getElementById("contenedor_cliente");
            if (inputCliente) inputCliente.value = "";
            if (contenedorCliente) contenedorCliente.style.display = "none";

            if (!idFactura) {
                selectProducto.innerHTML = '<option value="">Seleccione una factura primero</option>';
                return;
            }

            // URL AJAX
            const url = "/devolucion/obtener-productos/" + encodeURIComponent(idFactura) + "/";

            fetch(url)
                .then(function (response) {
                    if (!response.ok) throw new Error("Error en la respuesta del servidor");
                    return response.json();
                })
                .then(function (data) {
                    selectProducto.innerHTML = '<option value="">Seleccione un producto</option>';

                    if (data.productos && data.productos.length > 0) {
                        productosCache = data.productos; // Guardamos datos en caché local

                        data.productos.forEach(function (producto) {
                            const option = document.createElement("option");
                            option.value = producto.id;
                            option.textContent = producto.nombre;
                            selectProducto.appendChild(option);
                        });
                    } else {
                        selectProducto.innerHTML = '<option value="">No hay productos disponibles para devolver</option>';
                    }

                    // Mostrar cliente si viene en la respuesta de la factura
                    if (inputCliente && data.cliente) {
                        inputCliente.value = data.cliente;
                        if (contenedorCliente) contenedorCliente.style.display = "block";
                    }
                })
                .catch(function (error) {
                    console.error("Error al cargar productos:", error);
                    selectProducto.innerHTML = '<option value="">Error al cargar productos</option>';
                });
        });

        // Modificar dinámicamente los límites del Input "Cantidad" al cambiar de producto
        selectProducto.addEventListener("change", function () {
            const idProductoSeleccionado = parseInt(this.value);
            
            if (!idProductoSeleccionado) {
                resetearInputCantidad();
                return;
            }

            // Buscamos el producto seleccionado en la caché local para obtener su cantidad máxima
            const productoData = productosCache.find(p => p.id === idProductoSeleccionado);

            if (productoData) {
                inputCantidad.disabled = false;
                inputCantidad.min = 1;
                inputCantidad.max = productoData.max_cantidad;
                inputCantidad.value = 1;
                helperCantidad.textContent = `Cantidad máxima que puede devolver: ${productoData.max_cantidad}`;
            }
        });
    }

    function resetearInputCantidad() {
        if (inputCantidad) {
            inputCantidad.disabled = true;
            inputCantidad.value = "";
            inputCantidad.removeAttribute("max");
            inputCantidad.placeholder = "Seleccione un producto primero";
        }
        if (helperCantidad) {
            helperCantidad.textContent = "";
        }
    }

    // ==========================================================
    // VALIDACIÓN DEL FORMULARIO EN EL CLIENTE
    // ==========================================================
    const form = document.getElementById("formDevolucion");

    if (form) {
        form.addEventListener("submit", function (e) {

            if (selectFactura && !selectFactura.value) {
                e.preventDefault();
                alert("Seleccione una factura.");
                selectFactura.focus();
                return;
            }

            if (selectProducto && !selectProducto.value) {
                e.preventDefault();
                alert("Seleccione un producto.");
                selectProducto.focus();
                return;
            }

            if (inputCantidad) {
                const valor = parseInt(inputCantidad.value);
                const maximo = parseInt(inputCantidad.max);

                if (isNaN(valor) || valor < 1) {
                    e.preventDefault();
                    alert("Ingrese una cantidad válida mayor o igual a 1.");
                    inputCantidad.focus();
                    return;
                }

                if (maximo && valor > maximo) {
                    e.preventDefault();
                    alert(`No puede devolver una cantidad mayor a la comprada (${maximo}).`);
                    inputCantidad.focus();
                    return;
                }
            }
        });
    }
});