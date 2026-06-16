/* proveedor.js — Lógica de comportamiento y API de Proveedores */

function $(id) { 
  return document.getElementById(id); 
}

function getCsrf() {
  const el = document.querySelector("#csrfFormProveedor input[name=csrfmiddlewaretoken]");
  return el ? el.value : "";
}

function fillModal({ mode, idProveedor = "", nombre = "", telefono = "", email = "", contacto = "", direccion = "", tipo = "" }) {
  $("ep_mode").value = mode;
  $("ep_id_proveedor").value = idProveedor;
  $("ep_nombre").value = nombre;
  $("ep_telefono").value = telefono;
  $("ep_email").value = email;
  $("ep_contacto").value = contacto;
  $("ep_direccion").value = direccion;
  $("ep_tipo").value = tipo;
  $("ep_estado").value = arguments[0].estado || "Activo";

  const esNuevo = mode === "create";
  $("modalProveedorTitle").textContent = esNuevo ? "Nuevo proveedor" : "Editar proveedor";
  $("modalProveedorSubtitle").textContent = esNuevo
    ? "Completa los datos para registrar un proveedor nuevo"
    : "Actualiza los datos del proveedor seleccionado";
  $("btnGuardarProveedor").textContent = esNuevo ? "Crear proveedor" : "Guardar cambios";

  document.body.style.overflow = "hidden";
  $("modalProveedor").style.display = "flex";
}

function openModalFromButton(btn) {
  fillModal({
    mode: "edit",
    idProveedor: btn.dataset.id || "",
    nombre: btn.dataset.nombre || "",
    telefono: btn.dataset.telefono || "",
    email: btn.dataset.email || "",
    contacto: btn.dataset.contacto || "",
    direccion: btn.dataset.direccion || "",
    tipo: btn.dataset.tipo || "",
    estado: btn.dataset.estado || "",
  });
}

function closeModal() {
  $("modalProveedor").style.display = "none";
  document.body.style.overflow = "";
}

async function guardarProveedor() {
  const modo = $("ep_mode").value;
  const idProveedor = $("ep_id_proveedor").value.trim();
  const nombre = $("ep_nombre").value.trim();

  if (!nombre) {
    alert("El nombre del proveedor es requerido.");
    return;
  }

  if (modo !== "create" && !idProveedor) {
    alert("No se encontró el proveedor a editar.");
    return;
  }

  const form = new FormData();
  form.append("nombre", nombre);
  form.append("telefono", $("ep_telefono").value);
  form.append("email", $("ep_email").value);
  form.append("numero_contacto", $("ep_contacto").value);
  form.append("direccion", $("ep_direccion").value);
  form.append("tipo_proveedor", $("ep_tipo").value);
  form.append("estado", $("ep_estado").value);
  
  if (modo !== "create") {
    form.append("id_proveedor", idProveedor);
  }

  const btn = $("btnGuardarProveedor");
  btn.disabled = true;

  try {
    const endpoint = modo === "create"
      ? "/compras/api/proveedor/upsert/"
      : "/compras/api/proveedor/actualizar/";

    const r = await fetch(endpoint, {
      method: "POST",
      headers: { "X-CSRFToken": getCsrf() },
      body: form,
    });
    const j = await r.json().catch(() => ({}));

    if (!r.ok || !j.ok) {
      alert(j.error || (modo === "create" ? "No se pudo crear el proveedor." : "No se pudo actualizar el proveedor."));
      return;
    }

    closeModal();
    window.location.reload();
  } catch (e) {
    alert("Error de red o servidor.");
  } finally {
    btn.disabled = false;
  }
}

// Inicialización de Eventos al cargar el DOM
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".prov-edit-btn[data-id]").forEach((btn) => {
    btn.addEventListener("click", () => openModalFromButton(btn));
  });

  $("btnAbrirNuevoProveedor")?.addEventListener("click", () => {
    fillModal({ mode: "create" });
  });

  $("btnCloseModalProveedor")?.addEventListener("click", closeModal);
  $("modalProveedorBackdrop")?.addEventListener("click", closeModal);
  $("btnGuardarProveedor")?.addEventListener("click", guardarProveedor);

  // Sistema de Filtrado/Búsqueda en tiempo real
  const searchInput = $("provSearchInput");
  const tableActive = $("provTableActive");
  const tableInactive = $("provTableInactive");
  const emptyState = $("provResultsEmpty");

  if (searchInput && (tableActive || tableInactive)) {
    const rows = Array.from([tableActive, tableInactive].filter(Boolean).flatMap(t => Array.from(t.querySelectorAll("tbody .prov-row"))));
    
    const applyFilter = () => {
      const term = searchInput.value.trim().toLowerCase();
      let visibleCount = 0;

      rows.forEach((row) => {
        const text = (row.dataset.search || row.textContent || "").toLowerCase();
        const visible = !term || text.includes(term);
        row.style.display = visible ? "" : "none";
        if (visible) visibleCount += 1;
      });

      if (emptyState) {
        emptyState.style.display = visibleCount ? "none" : "block";
        emptyState.textContent = term
          ? "No se encontraron proveedores con ese criterio."
          : "No hay proveedores que coincidan con la búsqueda.";
      }
    };

    searchInput.addEventListener("input", applyFilter);
    applyFilter();
  }

  // Cerrar modal al presionar Esc
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && $("modalProveedor")?.style.display === "flex") {
      closeModal();
    }
  });
});