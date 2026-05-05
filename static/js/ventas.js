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
// 🛒 ESTADO GLOBAL
// ==============================
let carrito = [];
let clienteSeleccionado = null;

// 💱 MONEDA
let monedaActual = "NIO";
let tasa = 36.6;

document.addEventListener("DOMContentLoaded", () => {

    console.log("JS cargado ✅");

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
    const formCliente = document.getElementById("form-cliente");
    const btnNuevoCliente = document.getElementById("nuevo-cliente-btn");
    const btnGuardarCliente = document.getElementById("guardar-cliente");

    // ==============================
    // 💱 MONEDA
    // ==============================
    function simbolo() {
        return monedaActual === "USD" ? "$" : "C$";
    }

    function convertir(valor) {
        return monedaActual === "USD" ? valor / tasa : valor;
    }

    // ⚠️ SOLO cambia símbolos en totales (no en productos)
    function actualizarSimbolosTotales() {
        const s = simbolo();

        document.querySelectorAll(".total-currency").forEach(el => {
            el.innerText = s;
        });
    }

    currencySelect.addEventListener("change", () => {
        monedaActual = currencySelect.value;
        actualizarSimbolosTotales();
        renderCarrito();
    });

    fxRateInput.addEventListener("input", () => {
        tasa = parseFloat(fxRateInput.value) || 36.6;
        renderCarrito();
    });

    actualizarSimbolosTotales();

    // ==============================
    // 🔍 BUSCADOR
    // ==============================
    document.getElementById("search").addEventListener("input", function () {
        const query = this.value.toLowerCase();

        document.querySelectorAll(".product-card").forEach(card => {
            const nombre = card.querySelector(".nombre").innerText.toLowerCase();
            const categoria = card.querySelector(".categoria").innerText.toLowerCase();

            card.style.display =
                (nombre.includes(query) || categoria.includes(query))
                    ? "block"
                    : "none";
        });
    });

    // ==============================
    // ➕ AGREGAR AL CARRITO
    // ==============================
    document.querySelectorAll(".add-to-cart").forEach(btn => {
        btn.addEventListener("click", function () {

            const id = this.dataset.id;
            const nombre = this.dataset.nombre;
            const precio = parseFloat(this.dataset.precio); // SIEMPRE C$

            if (!id || !nombre || isNaN(precio)) {
                console.error("Producto inválido");
                return;
            }

            const existe = carrito.find(p => p.id == id);

            if (existe) {
                existe.cantidad++;
            } else {
                carrito.push({ id, nombre, precio, cantidad: 1 });
            }

            renderCarrito();
        });
    });

    // ==============================
    // 🧾 RENDER
    // ==============================
    function renderCarrito() {
        cartItems.innerHTML = "";

        if (carrito.length === 0) {
            cartItems.innerHTML = '<p class="empty">No hay productos</p>';
            actualizarTotales();
            return;
        }

        carrito.forEach((item, index) => {

            const totalItem = item.precio * item.cantidad; // base C$
            const totalConvertido = convertir(totalItem);

            const div = document.createElement("div");
            div.className = "cart-item";

            div.innerHTML = `
                <span>${item.nombre} (x${item.cantidad})</span>
                <span>${simbolo()}${totalConvertido.toFixed(2)}</span>
                <button onclick="eliminarItem(${index})">❌</button>
            `;

            cartItems.appendChild(div);
        });

        actualizarTotales();
    }

    window.eliminarItem = (index) => {
        carrito.splice(index, 1);
        renderCarrito();
    };

    // ==============================
    // 💰 TOTALES
    // ==============================
    function actualizarTotales() {

        const subtotalNIO = carrito.reduce((acc, p) => acc + p.precio * p.cantidad, 0);
        const ivaNIO = subtotalNIO * 0.15;
        const totalNIO = subtotalNIO + ivaNIO;

        subtotalEl.innerText = convertir(subtotalNIO).toFixed(2);
        ivaEl.innerText = convertir(ivaNIO).toFixed(2);
        totalEl.innerText = convertir(totalNIO).toFixed(2);

        calcularVuelto(convertir(totalNIO));
    }

    function calcularVuelto(total) {
        const recibido = parseFloat(cashInput.value) || 0;
        const cambio = recibido - total;

        changeEl.innerText = cambio >= 0 ? cambio.toFixed(2) : "0.00";
        payBtn.disabled = carrito.length === 0 || recibido < total;
    }

    cashInput.addEventListener("input", actualizarTotales);

    // ==============================
    // 👤 CLIENTES
    // ==============================
    btnNuevoCliente.addEventListener("click", () => {
        formCliente.style.display =
            formCliente.style.display === "block" ? "none" : "block";
    });

    inputCliente.addEventListener("input", () => {
        const q = inputCliente.value.trim();

        if (q.length < 2) {
            listaClientes.innerHTML = "";
            return;
        }

        fetch(`/ventas/buscar-cliente/?q=${q}`)
            .then(res => res.json())
            .then(data => {
                listaClientes.innerHTML = "";

                data.forEach(c => {
                    const li = document.createElement("li");
                    li.textContent = c.nombre;

                    li.onclick = () => {
                        clienteSeleccionado = c;
                        inputCliente.value = c.nombre;
                        listaClientes.innerHTML = "";
                    };

                    listaClientes.appendChild(li);
                });
            });
    });

    btnGuardarCliente.addEventListener("click", () => {

        const nombre = document.getElementById("nuevo-nombre").value.trim();
        const telefono = document.getElementById("nuevo-telefono").value.trim();
        const direccion = document.getElementById("nuevo-direccion").value.trim();

        if (!nombre || !direccion) return alert("Nombre y dirección requeridos");

        fetch('/ventas/crear-cliente/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ nombre, telefono, direccion })
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === "success") {
                clienteSeleccionado = data;
                inputCliente.value = data.nombre;
                formCliente.style.display = "none";
                alert("Cliente registrado ✅");
            } else {
                alert(data.message);
            }
        });
    });

    // ==============================
    // 💳 FINALIZAR
    // ==============================
    payBtn.addEventListener("click", () => {

        fetch(payBtn.dataset.url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie('csrftoken')
            },
            body: JSON.stringify({
                carrito,
                total: parseFloat(totalEl.innerText),
                moneda: monedaActual,
                tasa: tasa,
                cliente_id: clienteSeleccionado?.id || null
            })
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === "success") {
                alert("Venta guardada ✅");
                location.reload();
            } else {
                alert(data.message);
            }
        });
    });

    document.getElementById("cancel").addEventListener("click", () => {
        if (confirm("¿Cancelar venta?")) location.reload();
    });

});