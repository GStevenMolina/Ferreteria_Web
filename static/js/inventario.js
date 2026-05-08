// Módulo principal del inventario: gestiona la interacción de la página de registro de inventario.
// Se ejecuta en un IIFE para no contaminar el ámbito global.
(function () {
  // Verificar que la página de inventario existe antes de ejecutar cualquier lógica
  const page = document.querySelector('.inventory-page');
  if (!page) return;

  // Referencias a los elementos de búsqueda y filtro de la barra de herramientas
  const searchBox = document.getElementById('searchBox');
  const categoryFilter = document.getElementById('categoryFilter');

  // Lista de filas de la tabla de inventario
  const rows = Array.from(document.querySelectorAll('.inventory-row'));

  // Intenta analizar el JSON del atributo data-product de cada fila;
  // devuelve un objeto vacío si el valor es inválido o nulo
  function safeParse(raw) {
    try {
      return JSON.parse(raw || '{}');
    } catch (error) {
      return {};
    }
  }

  // Filtra las filas de la tabla según el texto de búsqueda y la categoría seleccionada
  function filterRows() {
    const term = (searchBox?.value || '').toLowerCase().trim();
    const category = categoryFilter?.value || '';

    rows.forEach((row) => {
      const data = safeParse(row.dataset.product);
      // Comparar la categoría del producto con el filtro activo
      const matchesCategory = !category || String(data.categoria || '') === String(category);
      // Buscar el término en el código y el nombre del producto
      const haystack = [data.codigo, data.nombre].join(' ').toLowerCase();
      const matchesTerm = !term || haystack.includes(term);
      // Mostrar u ocultar la fila según ambas condiciones
      row.style.display = matchesCategory && matchesTerm ? '' : 'none';
    });
  }

  // Debounced autocomplete for search box (updates datalist)
  let acTimeout = null;
  const acUrl = searchBox?.dataset.autocompleteUrl;
  const datalist = document.getElementById('search-suggestions');

  function updateDatalist(items) {
    if (!datalist) return;
    datalist.innerHTML = '';
    items.forEach((it) => {
      const option = document.createElement('option');
      option.value = `${it.id_producto} | ${it.nombre}`;
      datalist.appendChild(option);
    });
  }

  searchBox?.addEventListener('input', (e) => {
    // keep client-side filtering too
    filterRows();
    const q = (e.target.value || '').trim();
    if (!acUrl) return;
    if (acTimeout) clearTimeout(acTimeout);
    if (q.length < 2) {
      updateDatalist([]);
      return;
    }
    acTimeout = setTimeout(() => {
      fetch(`${acUrl}?q=${encodeURIComponent(q)}`)
        .then((r) => r.json())
        .then((data) => updateDatalist(data))
        .catch(() => {});
    }, 220);
  });

  categoryFilter?.addEventListener('change', () => {
    // submit the surrounding form to apply server-side filters
    const frm = categoryFilter.closest('form');
    if (frm) frm.requestSubmit();
    else filterRows();
  });

  // Aplicar los filtros iniciales al cargar la página (por si hay parámetros en la URL)
  filterRows();
})();