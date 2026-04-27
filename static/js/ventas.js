function toggleCliente(btn) {
  const form = document.getElementById("formNuevoCliente");

  form.classList.toggle("active");

  if (form.classList.contains("active")) {
    btn.textContent = "✖ Cancelar";
  } else {
    btn.textContent = "+ Nuevo Cliente";
  }
}