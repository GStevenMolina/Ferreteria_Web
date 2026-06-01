document.addEventListener("DOMContentLoaded", function () {

    // ==========================================================
    // BUSCADOR DE LA TABLA DE DEVOLUCIONES
    // ==========================================================
    const buscador = document.getElementById("buscador");

    if (buscador) {
        buscador.addEventListener("keyup", function () {
            const texto = this.value.toLowerCase();

            const filas = document.querySelectorAll(
                "#tablaDevoluciones tbody tr"
            );

            filas.forEach(function (fila) {
                const producto = fila.querySelector(".producto");

                // Ignorar fila vacía
                if (!producto) return;

                const nombreProducto =
                    producto.textContent.toLowerCase();

                fila.style.display =
                    nombreProducto.includes(texto)
                        ? ""
                        : "none";
            });
        });
    }

    // ==========================================================
    // SELECTS
    // ==========================================================
    const selectFactura = document.getElementById("id_factura");
    const selectProducto = document.getElementById("id_producto");

    // ==========================================================
    // CARGAR PRODUCTOS SEGÚN FACTURA (SIN REFRESCAR)
    // ==========================================================
    if (selectFactura && selectProducto) {

        selectFactura.addEventListener("change", function () {
            const idFactura = this.value;

            // Limpiar select de productos
            selectProducto.innerHTML =
                '<option value="">Cargando productos...</option>';

            // Limpiar cliente si existe
            const inputCliente =
                document.getElementById("cliente_factura");

            if (inputCliente) {
                inputCliente.value = "";
            }

            // Si no hay factura seleccionada
            if (!idFactura) {
                selectProducto.innerHTML =
                    '<option value="">Seleccione una factura primero</option>';
                return;
            }

            // URL AJAX
            const url =
                "/devolucion/obtener-productos/" +
                encodeURIComponent(idFactura) +
                "/";

            // Petición AJAX
            fetch(url)
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error(
                            "Error en la respuesta del servidor"
                        );
                    }

                    return response.json();
                })
                .then(function (data) {

                    // Limpiar select
                    selectProducto.innerHTML =
                        '<option value="">Seleccione un producto</option>';

                    // Agregar productos
                    if (
                        data.productos &&
                        data.productos.length > 0
                    ) {
                        data.productos.forEach(function (producto) {
                            const option =
                                document.createElement("option");

                            // IMPORTANTE:
                            // El backend devuelve:
                            // { id: ..., nombre: ... }
                            option.value = producto.id;
                            option.textContent =
                                producto.nombre;

                            selectProducto.appendChild(option);
                        });
                    } else {
                        selectProducto.innerHTML =
                            '<option value="">No hay productos en esta factura</option>';
                    }

                    // Mostrar cliente
                    if (
                        inputCliente &&
                        data.cliente
                    ) {
                        inputCliente.value =
                            data.cliente;
                    }
                })
                .catch(function (error) {
                    console.error(
                        "Error al cargar productos:",
                        error
                    );

                    selectProducto.innerHTML =
                        '<option value="">Error al cargar productos</option>';
                });
        });
    }

    // ==========================================================
    // VALIDACIÓN DEL FORMULARIO
    // ==========================================================
    const form = document.getElementById("formDevolucion");

    if (form) {
        form.addEventListener("submit", function (e) {

            // Validar factura
            if (
                selectFactura &&
                !selectFactura.value
            ) {
                e.preventDefault();
                alert("Seleccione una factura.");
                selectFactura.focus();
                return;
            }

            // Validar producto
            if (
                selectProducto &&
                !selectProducto.value
            ) {
                e.preventDefault();
                alert("Seleccione un producto.");
                selectProducto.focus();
                
                return;
            }

        });
    }

});