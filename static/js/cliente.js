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

    modalCliente.style.display = "flex";
}


// =========================================
// CERRAR MODAL
// =========================================
function cerrarModal() {

    modalCliente.style.display = "none";
}


// =========================================
// BOTON CERRAR
// =========================================
btnCerrarModalCliente.addEventListener(
    "click",
    cerrarModal
);


// =========================================
// CLICK BACKDROP
// =========================================
modalBackdrop.addEventListener(
    "click",
    cerrarModal
);


// =========================================
// VER CLIENTE
// =========================================
document.querySelectorAll(".btnVer")
.forEach(btn => {

    btn.addEventListener("click", () => {

        abrirModal();

        modalTitulo.textContent =
            "Información del Cliente";

        clienteNombre.value =
            btn.dataset.nombre;

        clienteTelefono.value =
            btn.dataset.telefono;

        clienteDireccion.value =
            btn.dataset.direccion;

        clienteNombre.readOnly = true;
        clienteTelefono.readOnly = true;
        clienteDireccion.readOnly = true;

        btnGuardarCliente.style.display = "none";
        btnEliminarCliente.style.display = "none";

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

        modalTitulo.textContent =
            "Editar Cliente";

        clienteNombre.value =
            btn.dataset.nombre;

        clienteTelefono.value =
            btn.dataset.telefono;

        clienteDireccion.value =
            btn.dataset.direccion;

        clienteNombre.readOnly = false;
        clienteTelefono.readOnly = false;
        clienteDireccion.readOnly = false;

        btnGuardarCliente.style.display =
            "inline-flex";

        btnEliminarCliente.style.display =
            "none";

        formCliente.action =
            `/cliente/editar/${id}/`;

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

        modalTitulo.textContent =
            "Eliminar Cliente";

        clienteNombre.value =
            btn.dataset.nombre;

        clienteTelefono.value =
            btn.dataset.telefono;

        clienteDireccion.value =
            btn.dataset.direccion;

        clienteNombre.readOnly = true;
        clienteTelefono.readOnly = true;
        clienteDireccion.readOnly = true;

        btnGuardarCliente.style.display =
            "none";

        btnEliminarCliente.style.display =
            "inline-flex";

        formCliente.action =
            `/cliente/eliminar/${id}/`;

    });

});

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