// =========================================
// MODAL CLIENTE
// =========================================
const modalCliente =
    document.getElementById("modalCliente");

const modalBackdrop =
    document.getElementById("modalBackdrop");

const btnCerrarModalCliente =
    document.getElementById("btnCerrarModalCliente");

const formCliente =
    document.getElementById("formCliente");

const modalTitulo =
    document.getElementById("modalTitulo");

const clienteNombre =
    document.getElementById("clienteNombre");

const clienteTelefono =
    document.getElementById("clienteTelefono");

const clienteDireccion =
    document.getElementById("clienteDireccion");

const btnGuardarCliente =
    document.getElementById("btnGuardarCliente");

const btnEliminarCliente =
    document.getElementById("btnEliminarCliente");


// =========================================
// ABRIR MODAL
// =========================================
function abrirModal() {
    if (modalCliente) {
        modalCliente.style.display = "flex";
    }
}


// =========================================
// CERRAR MODAL
// =========================================
function cerrarModal() {
    if (modalCliente) {
        modalCliente.style.display = "none";
    }
}


// =========================================
// BOTON CERRAR
// =========================================
btnCerrarModalCliente?.addEventListener(
    "click",
    cerrarModal
);


// =========================================
// CLICK BACKDROP
// =========================================
modalBackdrop?.addEventListener(
    "click",
    cerrarModal
);


// =========================================
// BUSCADOR DE CLIENTES
// =========================================
const buscador =
    document.querySelector(".search-input");

const filasClientes =
    document.querySelectorAll(
        ".clientes-table tbody tr"
    );


// =========================================
// EVENTO BUSCAR
// =========================================
if (buscador) {
    buscador.addEventListener("keyup", () => {

        const texto =
            buscador.value.toLowerCase();

        filasClientes.forEach(fila => {

            const contenido =
                fila.textContent.toLowerCase();

            // MOSTRAR / OCULTAR
            if (contenido.includes(texto)) {

                fila.style.display = "";

            } else {

                fila.style.display = "none";
            }

        });

    });
}


// =========================================
// VER CLIENTE
// =========================================
document.querySelectorAll(".btnVer")
.forEach(btn => {

    btn.addEventListener("click", () => {

        abrirModal();

        if (modalTitulo) modalTitulo.textContent = "Información del Cliente";

        if (clienteNombre) { clienteNombre.value = btn.dataset.nombre || ""; clienteNombre.readOnly = true; }
        if (clienteTelefono) { clienteTelefono.value = btn.dataset.telefono || ""; clienteTelefono.readOnly = true; }
        if (clienteDireccion) { clienteDireccion.value = btn.dataset.direccion || ""; clienteDireccion.readOnly = true; }

        if (btnGuardarCliente) btnGuardarCliente.style.display = "none";
        if (btnEliminarCliente) btnEliminarCliente.style.display = "none";

    });

});


// =========================================
// EDITAR CLIENTE
// =========================================
document.querySelectorAll(".btnEditar")
.forEach(btn => {

    btn.addEventListener("click", () => {

        const id = btn.dataset.id;

        abrirModal();

        if (modalTitulo) modalTitulo.textContent = "Editar Cliente";

        if (clienteNombre) { clienteNombre.value = btn.dataset.nombre || ""; clienteNombre.readOnly = false; }
        if (clienteTelefono) { clienteTelefono.value = btn.dataset.telefono || ""; clienteTelefono.readOnly = false; }
        if (clienteDireccion) { clienteDireccion.value = btn.dataset.direccion || ""; clienteDireccion.readOnly = false; }

        if (btnGuardarCliente) btnGuardarCliente.style.display = "inline-flex";
        if (btnEliminarCliente) btnEliminarCliente.style.display = "none";

        if (formCliente) formCliente.action = `/cliente/editar/${id}/`;

    });

});


// =========================================
// ELIMINAR CLIENTE
// =========================================
document.querySelectorAll(".btnEliminar")
.forEach(btn => {

    btn.addEventListener("click", () => {

        const id = btn.dataset.id;

        abrirModal();

        if (modalTitulo) modalTitulo.textContent = "Eliminar Cliente";

        if (clienteNombre) { clienteNombre.value = btn.dataset.nombre || ""; clienteNombre.readOnly = true; }
        if (clienteTelefono) { clienteTelefono.value = btn.dataset.telefono || ""; clienteTelefono.readOnly = true; }
        if (clienteDireccion) { clienteDireccion.value = btn.dataset.direccion || ""; clienteDireccion.readOnly = true; }

        if (btnGuardarCliente) btnGuardarCliente.style.display = "none";
        if (btnEliminarCliente) btnEliminarCliente.style.display = "inline-flex";

        if (formCliente) formCliente.action = `/cliente/eliminar/${id}/`;

    });

});