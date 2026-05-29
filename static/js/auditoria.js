// Comportamiento simple para el panel de auditoría
document.addEventListener('DOMContentLoaded', function () {
  // Resaltar fila al hacer click (selección)
  document.querySelectorAll('.table tbody tr').forEach(function (tr) {
    tr.addEventListener('click', function () {
      document.querySelectorAll('.table tbody tr').forEach(r => r.classList.remove('selected'));
      tr.classList.add('selected');
    });
  });

  // Añadir estilo para fila seleccionada
  const style = document.createElement('style');
  style.innerHTML = '.table tbody tr.selected { background:#eef8ff; }';
  document.head.appendChild(style);
});
