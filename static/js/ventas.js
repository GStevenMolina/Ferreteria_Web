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
                cookieValue = decodeURIComponent(
                    cookie.substring(name.length + 1)
                );
                break;
            }
        }
    }

    return cookieValue;
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

    // ==============================
    // 💱 MONEDA
    // ==============================
    function simbolo() {
        return monedaActual === "USD" ? "$" : "C$";
    }

    function convertir(valor) {
        return monedaActual === "USD"
            ? valor / tasa
            : valor;
    }

    function actualizarSimbolosTotales() {
        const s = simbolo();

        document.querySelectorAll(".total-currency").forEach(el => {
            el.textContent = s;
        });
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
    const searchInput = document.getElementById("search");

    if (searchInput) {
        searchInput.addEventListener("input", function () {
            const query = this.value.toLowerCase();

            document.querySelectorAll(".product-card").forEach(card => {
                const nombre =
                    card.querySelector(".nombre")?.innerText.toLowerCase() || "";

                const categoria =
                    card.querySelector(".categoria")?.innerText.toLowerCase() || "";

                card.style.display =
                    nombre.includes(query) || categoria.includes(query)
                        ? "block"
                        : "none";
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

            if (!id || !nombre || isNaN(precio)) {
                alert("Producto inválido");
                return;
            }

            const existente = carrito.find(p => p.id == id);

            if (existente) {
                existente.cantidad++;
            } else {
                carrito.push({
                    id: id,
                    nombre: nombre,
                    precio: precio, // precio base en C$
                    cantidad: 1
                });
            }

            renderCarrito();
        });
    });

    // ==============================
    // 🧾 RENDER DEL CARRITO
    // ==============================
    function renderCarrito() {
        if (!cartItems) return;

        cartItems.innerHTML = "";

        if (carrito.length === 0) {
            cartItems.innerHTML = '<p class="empty">No hay productos</p>';
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
            <span class="cart-price">
            ${simbolo()}${totalConvertido.toFixed(2)}
            </span>

            <button
            type="button"
            class="btn-remove"
            onclick="eliminarItem(${index})">
            x
            </button>
            </div>
            `;

            cartItems.appendChild(div);
        });

        actualizarTotales();
    }

    // ==============================
    // ❌ ELIMINAR ITEM
    // ==============================
    window.eliminarItem = function (index) {

    if (carrito[index].cantidad > 1) {
        carrito[index].cantidad--;
    } else {
        carrito.splice(index, 1);
    }

    renderCarrito();
};

    // ==============================
    // 💰 TOTALES
    // ==============================
    function actualizarTotales() {
        const subtotalNIO = carrito.reduce(
            (acc, item) => acc + (item.precio * item.cantidad),
            0
        );

        const ivaNIO = subtotalNIO * 0.15;
        const totalNIO = subtotalNIO + ivaNIO;

        if (subtotalEl) subtotalEl.textContent = convertir(subtotalNIO).toFixed(2);
        if (ivaEl) ivaEl.textContent = convertir(ivaNIO).toFixed(2);
        if (totalEl) totalEl.textContent = convertir(totalNIO).toFixed(2);

        calcularVuelto(convertir(totalNIO));
    }

    function calcularVuelto(total) {
        if (!cashInput || !changeEl || !payBtn) return;

        const recibido = parseFloat(cashInput.value) || 0;
        const cambio = recibido - total;

        changeEl.textContent =
            cambio >= 0
                ? cambio.toFixed(2)
                : "0.00";

        payBtn.disabled =
            carrito.length === 0 ||
            recibido < total ||
            !clienteSeleccionado;
    }

    if (cashInput) {
        cashInput.addEventListener("input", actualizarTotales);
    }

    // ==============================
// 👤 MODAL NUEVO CLIENTE
// ==============================
if (btnNuevoCliente) {
    btnNuevoCliente.addEventListener("click", () => {
        clienteModal.style.display = "flex";
    });
}

if (cerrarModal) {
    cerrarModal.addEventListener("click", () => {
        clienteModal.style.display = "none";
    });
}

window.addEventListener("click", (e) => {
    if (e.target === clienteModal) {
        clienteModal.style.display = "none";
    }
});
    

    // ==============================
    // 🔍 BUSCAR CLIENTE
    // ==============================
    if (inputCliente) {
        inputCliente.addEventListener("input", () => {
            const q = inputCliente.value.trim();

            if (q.length < 2) {
                if (listaClientes) listaClientes.innerHTML = "";
                return;
            }

            fetch(`/ventas/buscar-cliente/?q=${encodeURIComponent(q)}`)
                .then(res => res.json())
                .then(data => {
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
                });
        });
    }

    // ==============================
    // 💾 GUARDAR CLIENTE
    // ==============================
    if (btnGuardarCliente) {
        btnGuardarCliente.addEventListener("click", () => {

            const nombre =
                document.getElementById("nuevo-nombre")?.value.trim() || "";

            const telefono =
                document.getElementById("nuevo-telefono")?.value.trim() || "";

            const direccion =
                document.getElementById("nuevo-direccion")?.value.trim() || "";

            if (!nombre || !direccion) {
                alert("Nombre y dirección son obligatorios.");
                return;
            }

            fetch("/ventas/crear-cliente/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCookie("csrftoken")
                },
                body: JSON.stringify({
                    nombre,
                    telefono,
                    direccion
                })
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status === "success") {
                        clienteSeleccionado = {
                            id: data.id,
                            nombre: data.nombre
                        };

                        if (inputCliente) {
                            inputCliente.value = data.nombre;
                        }

                        if (clienteModal) {
                            clienteModal.style.display = "none";
                        }

                        document.getElementById("nuevo-nombre").value = "";
                        document.getElementById("nuevo-telefono").value = "";
                        document.getElementById("nuevo-direccion").value = "";

                        alert("Cliente registrado correctamente ✅");

                        actualizarTotales();
                    } else {
                        alert(data.message || "Error al guardar cliente");
                    }
                });
        });
    }

    // ==============================
    // 💳 FINALIZAR VENTA
    // ==============================
    if (payBtn) {
        payBtn.addEventListener("click", () => {

            if (!clienteSeleccionado) {
                alert("Debe seleccionar un cliente.");
                return;
            }

            if (carrito.length === 0) {
                alert("El carrito está vacío.");
                return;
            }

            const total = parseFloat(totalEl.textContent || "0");
            const deseaEnvio = confirm("¿Desea envío a domicilio?");

            fetch(payBtn.dataset.url, {
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
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status === "success") {

                        alert(
                            `Venta guardada correctamente.\n` +
                            `Factura: ${data.numero_factura}`
                        );

                        // Abrir PDF automáticamente
                        if (data.pdf_url) {
                            window.open(data.pdf_url, "_blank");
                        }

                        // Recargar página
                        setTimeout(() => {
                            location.reload();
                        }, 1000);

                    } else {
                        alert(data.message || "Error al guardar la venta.");
                    }
                })
                .catch(error => {
                    console.error(error);
                    alert("Error de comunicación con el servidor.");
                });
        });
    }

    // ==============================
    // ❌ CANCELAR
    // ==============================
    if (cancelBtn) {
        cancelBtn.addEventListener("click", () => {
            if (confirm("¿Cancelar la venta actual?")) {
                location.reload();
            }
        });
    }

    // ==============================
    // 🔄 INICIALIZAR
    // ==============================
    renderCarrito();
});