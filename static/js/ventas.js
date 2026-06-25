
// ==============================
// 🛡️ CSRF TOKEN
// ==============================
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            cookie = cookie.trim();
            if (cookie.startsWith(name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// ==============================
// 🛠️ UTILIDADES (Evita saturar el servidor)
// ==============================
function debounce(func, delay) {
    let timeoutId;
    return function (...args) {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => func.apply(this, args), delay);
    };
}

// ==============================
// 🛒 ESTADO GLOBAL
// ==============================
let carrito = [];
let clienteSeleccionado = null;

// 💱 MONEDA
let monedaActual = "NIO";
let tasa = 36.5;

// ==============================
// 🚀 INICIO
// ==============================
document.addEventListener("DOMContentLoaded", () => {
    console.log("ventas.js cargado correctamente ✅");

    // ==============================
    // 🔗 ELEMENTOS
    // ==============================
    const cartItems = document.getElementById("cart-items");
    const subtotalEl = document.getElementById("subtotal");
    const ivaEl = document.getElementById("iva");
    const totalEl = document.getElementById("total");
    const changeEl = document.getElementById("change");
    const cashInput = document.getElementById("cash-received");
    const payBtn = document.getElementById("pay");

    const currencySelect = document.getElementById("currencySelect");
    const fxRateInput = document.getElementById("fxRate");

    const inputCliente = document.getElementById("buscar-cliente");
    const listaClientes = document.getElementById("lista-clientes");

    const clienteModal = document.getElementById("clienteModal");
    const cerrarModal = document.querySelector(".cerrar-modal");
    
    const btnNuevoCliente = document.getElementById("nuevo-cliente-btn");
    const btnGuardarCliente = document.getElementById("guardar-cliente");

    const cancelBtn = document.getElementById("cancel");
    const searchInput = document.getElementById("search");

    // ==============================
    // 💱 MONEDA
    // ==============================
    function simbolo() { return monedaActual === "USD" ? "$" : "C$"; }
    function convertir(valor) { return monedaActual === "USD" ? valor / tasa : valor; }

    function actualizarSimbolosTotales() {
        const s = simbolo();
        document.querySelectorAll(".total-currency").forEach(el => { el.textContent = s; });
    }

    if (currencySelect) {
        currencySelect.addEventListener("change", () => {
            monedaActual = currencySelect.value;
            actualizarSimbolosTotales();
            renderCarrito();
        });
    }

    if (fxRateInput) {
        fxRateInput.addEventListener("input", () => {
            tasa = parseFloat(fxRateInput.value) || 36.5;
            renderCarrito();
        });
    }

    actualizarSimbolosTotales();

    // ==============================
    // 🔍 BUSCADOR DE PRODUCTOS
    // ==============================
    if (searchInput) {
        searchInput.addEventListener("input", function () {
            const query = this.value.toLowerCase();
            document.querySelectorAll(".product-card").forEach(card => {
                const nombre = card.querySelector(".nombre")?.innerText.toLowerCase() || "";
                const categoria = card.querySelector(".categoria")?.innerText.toLowerCase() || "";
                card.style.display = nombre.includes(query) || categoria.includes(query) ? "block" : "none";
            });
        });
    }

    // ==============================
    // ➕ AGREGAR PRODUCTO
    // ==============================
    document.querySelectorAll(".add-to-cart").forEach(btn => {
        btn.addEventListener("click", function () {
            const id = this.dataset.id;
            const nombre = this.dataset.nombre;
            const precio = parseFloat(this.dataset.precio);
            let stockActual = parseInt(this.dataset.stock);

            if (!id || !nombre || isNaN(precio)) {
                Swal.fire({ icon: 'error', title: 'Error', text: 'Producto inválido' });
                return;
            }

            if (stockActual > 0) {
                stockActual--;
                this.dataset.stock = stockActual;
                
                const stockElemento = document.getElementById(`stock-${id}`);
                if (stockElemento) stockElemento.textContent = stockActual;

                const existente = carrito.find(p => p.id == id);
                if (existente) {
                    existente.cantidad++;
                } else {
                    carrito.push({ id, nombre, precio, cantidad: 1 });
                }
                renderCarrito();
            } else {
                Swal.fire({
                    icon: 'warning',
                    title: 'Stock Agotado',
                    text: `No hay unidades disponibles de: ${nombre}`,
                    confirmButtonColor: '#3b82f6'
                });
            }
        });
    });

    // ==============================
    // 🧾 RENDER DEL CARRITO
    // ==============================
    function renderCarrito() {
        if (!cartItems) return;
        cartItems.innerHTML = "";

        if (carrito.length === 0) {
            cartItems.innerHTML = '<p class="empty">No hay productos en la lista</p>';
            actualizarTotales();
            return;
        }

        carrito.forEach((item, index) => {
            const totalItem = item.precio * item.cantidad;
            const totalConvertido = convertir(totalItem);

            const div = document.createElement("div");
            div.className = "cart-item";
            div.innerHTML = `
            <div class="cart-item-info">
                <strong>${item.nombre}</strong>
                <small>Cantidad: ${item.cantidad}</small>
            </div>
            <div class="cart-item-actions">
                <span class="cart-price">${simbolo()}${totalConvertido.toFixed(2)}</span>
                <button type="button" class="btn-remove" onclick="eliminarItem(${index})">x</button>
            </div>`;
            cartItems.appendChild(div);
        });
        actualizarTotales();
    }

    // ==============================
    // ❌ ELIMINAR ITEM
    // ==============================
    window.eliminarItem = function (index) {
        const item = carrito[index];
        const btnAgregado = document.querySelector(`.add-to-cart[data-id="${item.id}"]`);
        
        if (btnAgregado) {
            let stockActual = parseInt(btnAgregado.dataset.stock);
            stockActual++;
            btnAgregado.dataset.stock = stockActual;
            const stockElemento = document.getElementById(`stock-${item.id}`);
            if (stockElemento) stockElemento.textContent = stockActual;
        }

        if (item.cantidad > 1) item.cantidad--;
        else carrito.splice(index, 1);

        renderCarrito();
    };

    // ==============================
    // 💰 TOTALES
    // ==============================
    function actualizarTotales() {
        const subtotalNIO = carrito.reduce((acc, item) => acc + (item.precio * item.cantidad), 0);
        const ivaNIO = Number((subtotalNIO * 0.15).toFixed(2));
        const totalNIO = Number((subtotalNIO + ivaNIO).toFixed(2));

        if (subtotalEl) subtotalEl.textContent = convertir(subtotalNIO).toFixed(2);
        if (ivaEl) ivaEl.textContent = convertir(ivaNIO).toFixed(2);
        if (totalEl) totalEl.textContent = convertir(totalNIO).toFixed(2);

        calcularVuelto(convertir(totalNIO));
    }

    function calcularVuelto(total) {
        if (!cashInput || !changeEl || !payBtn) return;
        const recibido = parseFloat(cashInput.value) || 0;
        const cambio = recibido - total;

        changeEl.textContent = cambio >= 0 ? cambio.toFixed(2) : "0.00";
        payBtn.disabled = carrito.length === 0 || recibido < total || !clienteSeleccionado;
    }

    if (cashInput) cashInput.addEventListener("input", actualizarTotales);

    // ==============================
    // 👤 MODAL NUEVO CLIENTE
    // ==============================
    if (btnNuevoCliente) btnNuevoCliente.addEventListener("click", () => clienteModal.style.display = "flex");
    if (cerrarModal) cerrarModal.addEventListener("click", () => clienteModal.style.display = "none");
    window.addEventListener("click", (e) => { if (e.target === clienteModal) clienteModal.style.display = "none"; });

    // ==============================
    // 🔍 BUSCAR CLIENTE (CON DEBOUNCE)
    // ==============================
    if (inputCliente) {
        inputCliente.addEventListener("input", debounce(async () => {
            const q = inputCliente.value.trim();
            if (q.length < 2) {
                if (listaClientes) listaClientes.innerHTML = "";
                return;
            }

            try {
                const res = await fetch(`/ventas/buscar-cliente/?q=${encodeURIComponent(q)}`);
                const data = await res.json();
                if (!listaClientes) return;
                
                listaClientes.innerHTML = "";
                data.forEach(cliente => {
                    const li = document.createElement("li");
                    li.textContent = cliente.nombre;
                    li.addEventListener("click", () => {
                        clienteSeleccionado = cliente;
                        inputCliente.value = cliente.nombre;
                        listaClientes.innerHTML = "";
                        actualizarTotales();
                    });
                    listaClientes.appendChild(li);
                });
            } catch (error) {
                console.error("Error al buscar cliente:", error);
            }
        }, 300));
    }

    // ==============================
    // 💾 GUARDAR CLIENTE
    // ==============================
    if (btnGuardarCliente) {
        btnGuardarCliente.addEventListener("click", async () => {
            const nombre = document.getElementById("nuevo-nombre")?.value.trim() || "";
            const telefono = document.getElementById("nuevo-telefono")?.value.trim() || "";
            const direccion = document.getElementById("nuevo-direccion")?.value.trim() || "";

            if (!nombre || !direccion) {
                Swal.fire({ icon: 'warning', title: 'Datos incompletos', text: 'El nombre y la dirección son obligatorios.', confirmButtonColor: '#3b82f6' });
                return;
            }

            btnGuardarCliente.disabled = true;
            btnGuardarCliente.textContent = "Guardando...";

            try {
                const res = await fetch("/ventas/crear-cliente/", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": getCookie("csrftoken")
                    },
                    body: JSON.stringify({ nombre, telefono, direccion })
                });
                
                const data = await res.json();

                if (data.status === "success") {
                    clienteSeleccionado = { id: data.id, nombre: data.nombre };
                    if (inputCliente) inputCliente.value = data.nombre;
                    if (clienteModal) clienteModal.style.display = "none";

                    document.getElementById("nuevo-nombre").value = "";
                    document.getElementById("nuevo-telefono").value = "";
                    document.getElementById("nuevo-direccion").value = "";

                    Swal.fire({
                        icon: 'success',
                        title: '¡Cliente Registrado!',
                        text: 'El perfil se configuró como activo por defecto.',
                        timer: 2000,
                        showConfirmButton: false
                    });
                    actualizarTotales();
                } else {
                    Swal.fire({ icon: 'error', title: 'Error', text: data.message || "No se pudo guardar el cliente." });
                }
            } catch (error) {
                Swal.fire({ icon: 'error', title: 'Error de Red', text: "No se pudo comunicar con el servidor." });
            } finally {
                btnGuardarCliente.disabled = false;
                btnGuardarCliente.textContent = "Guardar";
            }
        });
    }

    // ==============================
    // 💳 FINALIZAR VENTA
    // ==============================
    if (payBtn) {
        payBtn.addEventListener("click", async () => {
            if (!clienteSeleccionado) {
                Swal.fire({ icon: 'info', title: 'Falta Cliente', text: 'Debe asignar un cliente a la orden.', confirmButtonColor: '#3b82f6' });
                return;
            }

            if (carrito.length === 0) {
                Swal.fire({ icon: 'info', title: 'Carrito Vacío', text: 'Agregue productos para procesar el pago.', confirmButtonColor: '#3b82f6' });
                return;
            }

            const total = parseFloat(totalEl.textContent || "0");
            
            // Reemplazo del confirm() tradicional
            const confirmacionEnvio = await Swal.fire({
                title: '¿Gestionar envío?',
                text: "¿Esta orden requiere envío a domicilio?",
                icon: 'question',
                showCancelButton: true,
                confirmButtonColor: '#3b82f6',
                cancelButtonColor: '#4b5563',
                confirmButtonText: 'Sí, con envío',
                cancelButtonText: 'No, retirar en local'
            });

            const deseaEnvio = confirmacionEnvio.isConfirmed;

            payBtn.disabled = true;
            payBtn.textContent = "Procesando...";

            try {
                const res = await fetch(payBtn.dataset.url, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": getCookie("csrftoken")
                    },
                    body: JSON.stringify({
                        carrito: carrito,
                        total: total,
                        moneda: monedaActual,
                        tasa: tasa,
                        cliente_id: clienteSeleccionado.id,
                        envio: deseaEnvio
                    })
                });

                const data = await res.json();

                if (data.status === "success") {
                    Swal.fire({
                        icon: 'success',
                        title: 'Operación Exitosa',
                        text: `Factura generada: ${data.numero_factura}`,
                        confirmButtonColor: '#10b981',
                        confirmButtonText: 'Imprimir y Continuar'
                    }).then(() => {
                        if (data.pdf_url) window.open(data.pdf_url, "_blank");
                        location.reload();
                    });
                } else {
                    Swal.fire({ icon: 'error', title: 'Error', text: data.message || "Hubo un problema al registrar la salida." });
                    payBtn.disabled = false;
                    payBtn.textContent = "Cobrar";
                }
            } catch (error) {
                Swal.fire({ icon: 'error', title: 'Error Crítico', text: "Fallo de comunicación con el servidor." });
                payBtn.disabled = false;
                payBtn.textContent = "Cobrar";
            }
        });
    }

    // ==============================
    // ❌ CANCELAR
    // ==============================
    if (cancelBtn) {
        cancelBtn.addEventListener("click", async () => {
            if (carrito.length === 0) return; // Si está vacío, no hacer nada

            // Reemplazo del confirm() tradicional
            const cancelar = await Swal.fire({
                title: '¿Limpiar módulo?',
                text: "Se perderán los artículos actuales y deberás iniciar de nuevo.",
                icon: 'warning',
                showCancelButton: true,
                confirmButtonColor: '#ef4444',
                cancelButtonColor: '#4b5563',
                confirmButtonText: 'Sí, cancelar todo',
                cancelButtonText: 'Volver a la venta'
            });

            if (cancelar.isConfirmed) {
                location.reload();
            }
        });
    }

    // ==============================
    // 🔄 INICIALIZAR
    // ==============================
    renderCarrito();
});