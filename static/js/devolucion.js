document.addEventListener("DOMContentLoaded", function () {

    // ==========================================================
    // 🔍 BUSCADOR DE LA TABLA DE HISTORIAL DE DEVOLUCIONES
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
    // ⚙️ SELECTS E INPUTS DE CONTROL DINÁMICO
    // ==========================================================
    const selectFactura = document.getElementById("id_factura");
    const selectProducto = document.getElementById("id_producto");
    const inputCantidad = document.getElementById("cantidad");
    const helperCantidad = document.getElementById("helper-cantidad");
    const estadoSelector = document.getElementById("estado_selector");
    const btnAñadir = document.getElementById("btnAñadirProducto");
    const cuerpoLista = document.getElementById("cuerpoListaDevolucion");
    const form = document.getElementById("formDevolucion");
    
    // Almacenará los productos de la factura activa con sus topes de cantidad
    let productosCache = []; 

    // ==========================================================
    // 📥 CARGAR PRODUCTOS SEGÚN FACTURA (AJAX NATIVO)
    // ==========================================================
    if (selectFactura && selectProducto) {

        selectFactura.addEventListener("change", function () {
            const idFactura = this.value;

            // Resetear estados y limpiar la tabla si cambian de factura
            selectProducto.innerHTML = '<option value="">Cargando productos...</option>';
            resetearInputCantidad();
            productosCache = [];
            if (cuerpoLista) {
                cuerpoLista.innerHTML = '<tr id="fila-vacia-lista"><td colspan="4" style="text-align: center; color: #999;">Ningún producto añadido todavía.</td></tr>';
            }

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

            // Buscamos el producto en la caché local para fijar el max real de la factura
            const productoData = productosCache.find(p => p.id === idProductoSeleccionado);

            if (productoData) {
                inputCantidad.disabled = false;
                inputCantidad.min = 1;
                inputCantidad.max = productoData.max_cantidad;
                inputCantidad.value = 1;
                helperCantidad.textContent = `Cantidad disponible en factura: ${productoData.max_cantidad}`;
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
    // ➕ LÓGICA PARA AÑADIR PRODUCTOS A LA TABLA DINÁMICA
    // ==========================================================
    if (btnAñadir && cuerpoLista) {
        btnAñadir.addEventListener("click", function () {
            // Lectura directa forzada desde el DOM actual para evitar desincronizaciones
            const selectProductoReal = document.getElementById("id_producto");
            const inputCantidadReal = document.getElementById("cantidad");

            const prodId = selectProductoReal ? selectProductoReal.value : "";
            const cant = inputCantidadReal ? parseInt(inputCantidadReal.value) : 0;
            
            // 1. Validar selección de producto
            if (!prodId || prodId === "" || selectProductoReal.selectedIndex === -1) {
                alert("Por favor, selecciona un producto válido.");
                return;
            }

            // 2. Validar cantidad coherente escrita
            if (isNaN(cant) || cant <= 0) {
                alert("Por favor, ingresa una cantidad válida mayor a 0.");
                return;
            }

            const prodNombre = selectProductoReal.options[selectProductoReal.selectedIndex].text;
            const maxCant = parseInt(inputCantidadReal.max) || 99999; 
            const esDefectuosoVal = estadoSelector ? estadoSelector.value : "false";

            // 3. Validar contra el máximo permitido en factura
            if (cant > maxCant) {
                alert(`No puedes devolver una cantidad mayor a la registrada en la factura (${maxCant}).`);
                return;
            }

            // Evitar duplicados en la tabla de preparación
            if (document.querySelector(`input[name="id_producto"][value="${prodId}"]`)) {
                alert("Este producto ya está en la lista de preparación.");
                return;
            }

            // Quitar el aviso de "Ningún producto añadido todavía"
            const filaVacia = document.getElementById("fila-vacia-lista");
            if (filaVacia) filaVacia.remove();

            // Construir nueva fila con los inputs preparados para Django (.getlist)
            const nuevaFila = document.createElement("tr");
            nuevaFila.innerHTML = `
                <td>
                    <strong>${prodNombre}</strong>
                    <input type="hidden" name="id_producto" value="${prodId}">
                </td>
                <td>
                    <span>${cant}</span>
                    <input type="hidden" name="cantidad" value="${cant}">
                </td>
                <td>
                    <span style="color: ${esDefectuosoVal === 'true' ? '#ef4444' : '#21a34a'}; font-weight: bold;">
                        ${esDefectuosoVal === 'true' ? '⚠️ DAÑADO' : '✓ Normal'}
                    </span>
                    <input type="hidden" name="es_defectuoso" value="${esDefectuosoVal}">
                </td>
                <td>
                    <button type="button" class="btn-quitar-fila">Quitar</button>
                </td>
            `;

            // Configurar el botón "Quitar" de la fila recién creada
            nuevaFila.querySelector(".btn-quitar-fila").addEventListener("click", function () {
                nuevaFila.remove();
                if (cuerpoLista.children.length === 0) {
                    cuerpoLista.innerHTML = '<tr id="fila-vacia-lista"><td colspan="4" style="text-align: center; color: #999;">Ningún producto añadido todavía.</td></tr>';
                }
            });

            cuerpoLista.appendChild(nuevaFila);

            // Resetear únicamente el bloque de selección rápida para el siguiente artículo
            selectProductoReal.value = "";
            resetearInputCantidad();
        });
    }

    // ==========================================================
    // 🛡️ VALIDACIÓN DEL SUBMIT FINAL (LISTA COMPLETA)
    // ==========================================================
    if (form) {
        form.addEventListener("submit", function (e) {
            // Validar que la tabla contenga al menos un producto inyectado
            const productosCargados = document.querySelectorAll('input[name="id_producto"]');
            
            if (productosCargados.length === 0) {
                e.preventDefault();
                alert("Operación cancelada: Agrega al menos un artículo a la lista de devolución antes de registrar.");
                return;
            }

            // Limpieza diferida: Se ejecuta justo después de que el formulario se dispara al backend
            setTimeout(function () {
                form.reset();
                resetearInputCantidad();
                productosCache = [];
                
                // 🧹 LIMPIEZA EXPLÍCITA DE LA TABLA DINÁMICA
                if (cuerpoLista) {
                    cuerpoLista.innerHTML = '<tr id="fila-vacia-lista"><td colspan="4" style="text-align: center; color: #999;">Ningún producto añadido todavía.</td></tr>';
                }

                // Mantener consistencia con la fecha de hoy tras el reset
                const fechaInput = document.getElementById("fecha");
                if (fechaInput) {
                    const hoy = new Date().toISOString().split("T")[0];
                    fechaInput.value = hoy;
                }

                // Ocultar bloque del cliente
                const contenedorCliente = document.getElementById("contenedor_cliente");
                if (contenedorCliente) contenedorCliente.style.display = "none";
                
                if (selectProducto) {
                    selectProducto.innerHTML = '<option value="">Seleccione una factura primero</option>';
                }
            }, 100);
        });
    }
});