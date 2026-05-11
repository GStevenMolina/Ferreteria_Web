// Módulo principal del inventario: gestiona la interacción de la página de registro de inventario.
// Se ejecuta en un IIFE para no contaminar el ámbito global.
(function () {
  // Verificar que la página de inventario existe antes de ejecutar cualquier lógica
  const page = document.querySelector('.inventory-page');
  if (!page) return;

  // Referencias a los elementos de búsqueda y filtro de la barra de herramientas
  const searchBox = document.getElementById('searchBox');
  const categoryFilter = document.getElementById('categoryFilter');
  const sortFilter = document.getElementById('sortFilter');
  const perPageSelect = document.getElementById('perPageSelect');

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
  const suggestionsBox = document.getElementById('searchSuggestions');
  let suggestionIndex = -1;

  function updateDatalist(items) {
    if (!datalist) return;
    datalist.innerHTML = '';
    items.forEach((it) => {
      const option = document.createElement('option');
      option.value = `${it.id_producto} | ${it.nombre}`;
      datalist.appendChild(option);
    });
  }

  function renderSuggestions(items) {
    if (!suggestionsBox) return;
    suggestionsBox.innerHTML = '';
    if (!items || items.length === 0) {
      suggestionsBox.style.display = 'none';
      suggestionIndex = -1;
      return;
    }
    items.forEach((it, i) => {
      const el = document.createElement('div');
      el.className = 'search-suggestions__item';
      el.setAttribute('role', 'option');
      el.dataset.value = `${it.id_producto} | ${it.nombre}`;
      el.dataset.id = it.id_producto;
      el.innerText = `${it.id_producto} | ${it.nombre}`;
      el.addEventListener('click', () => {
        searchBox.value = el.dataset.value;
        suggestionsBox.style.display = 'none';
        const frm = searchBox.closest('form');
        if (frm) frm.requestSubmit();
      });
      suggestionsBox.appendChild(el);
    });
    suggestionsBox.style.display = 'block';
    suggestionIndex = -1;
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
        .then((data) => { updateDatalist(data); renderSuggestions(data); })
        .catch(() => {});
    }, 220);
  });

  // Keyboard navigation for suggestions
  searchBox?.addEventListener('keydown', (e) => {
    if (!suggestionsBox || suggestionsBox.style.display === 'none') return;
    const items = Array.from(suggestionsBox.children);
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      suggestionIndex = Math.min(suggestionIndex + 1, items.length - 1);
      items.forEach((it, idx) => it.classList.toggle('is-active', idx === suggestionIndex));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      suggestionIndex = Math.max(suggestionIndex - 1, 0);
      items.forEach((it, idx) => it.classList.toggle('is-active', idx === suggestionIndex));
    } else if (e.key === 'Enter') {
      if (suggestionIndex >= 0 && items[suggestionIndex]) {
        e.preventDefault();
        const el = items[suggestionIndex];
        searchBox.value = el.dataset.value;
        suggestionsBox.style.display = 'none';
        const frm = searchBox.closest('form');
        if (frm) frm.requestSubmit();
      }
    } else if (e.key === 'Escape') {
      suggestionsBox.style.display = 'none';
      suggestionIndex = -1;
    }
  });

  categoryFilter?.addEventListener('change', () => {
    // submit the surrounding form to apply server-side filters
    const frm = categoryFilter.closest('form');
    if (frm) frm.requestSubmit();
    else filterRows();
  });

  sortFilter?.addEventListener('change', () => {
    const frm = sortFilter.closest('form');
    if (frm) frm.requestSubmit();
  });

  perPageSelect?.addEventListener('change', () => {
    const frm = perPageSelect.closest('form');
    if (frm) frm.requestSubmit();
  });

  // Quick edit modal logic
  const quickModal = document.getElementById('quickEditModal');
  const quickForm = document.getElementById('quickEditForm');
  const quickId = document.getElementById('quick_id_producto');
  const quickNombre = document.getElementById('quick_nombre');
  const quickPrecio = document.getElementById('quick_precio');
  const quickStockMin = document.getElementById('quick_stock_minimo');

  function getCookie(name) {
    const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return v ? v.pop() : '';
  }

  function openQuickModal(data, rowEl) {
    if (!quickModal) return;
    quickId.value = data.codigo || '';
    quickNombre.value = data.nombre || '';
    quickPrecio.value = data.precio_venta || '';
    quickStockMin.value = data.stock_minimo || '';
    quickModal.style.display = 'flex';
    quickModal.setAttribute('aria-hidden', 'false');
    // store current row for update
    quickModal._currentRow = rowEl;
  }

  function closeQuickModal() {
    if (!quickModal) return;
    quickModal.style.display = 'none';
    quickModal.setAttribute('aria-hidden', 'true');
    quickModal._currentRow = null;
  }

  document.querySelectorAll('[data-action="close-quick-modal"]').forEach((b) => b.addEventListener('click', closeQuickModal));

  // Open quick edit on button click
  document.querySelectorAll('[data-action="quick-edit"]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      const row = btn.closest('tr');
      const data = safeParse(row.dataset.product);
      openQuickModal(data, row);
    });
  });

  quickForm?.addEventListener('submit', (e) => {
    e.preventDefault();
    const payload = {
      id_producto: quickId.value,
      nombre: quickNombre.value,
      precio_venta: quickPrecio.value,
      stock_minimo: quickStockMin.value,
    };
    fetch('/registro/api/quick_update/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify(payload),
    })
      .then((r) => r.json())
      .then((json) => {
        if (json && json.ok) {
          // update row in-place
          const row = quickModal._currentRow;
          if (row) {
            const data = safeParse(row.dataset.product);
            if (payload.nombre) {
              data.nombre = payload.nombre;
              row.children[1].innerText = payload.nombre;
            }
            if (payload.precio_venta) {
              data.precio_venta = payload.precio_venta;
              row.children[3].innerText = `$${parseFloat(payload.precio_venta).toFixed(2)}`;
            }
            if (payload.stock_minimo) {
              data.stock_minimo = parseInt(payload.stock_minimo, 10) || data.stock_minimo;
              row.children[5].innerText = data.stock_minimo;
            }
            row.dataset.product = JSON.stringify(data);
          }
          closeQuickModal();
        } else {
          alert('Error: ' + (json.error || 'No se pudo guardar'));
        }
      })
      .catch(() => alert('Error de red al guardar'));
  });

  // Aplicar los filtros iniciales al cargar la página (por si hay parámetros en la URL)
  filterRows();
})();