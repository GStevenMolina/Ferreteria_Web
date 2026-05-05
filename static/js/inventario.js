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

  // Formularios y campos principales del panel lateral
  const productForm = document.getElementById('product-form');
  const createModal = document.getElementById('createProductModal');
  const createForm = document.getElementById('create-product-form');
  const movementProductInput = document.getElementById('movementProductInput');
  const deleteProductId = document.getElementById('deleteProductId');

  // Abre el modal para agregar un producto nuevo y reinicia el formulario
  function openCreateModal() {
    if (!createModal) return;
    createModal.classList.add('is-open');
    createModal.setAttribute('aria-hidden', 'false');
    createForm?.reset();
    createForm?.querySelector('[name="nombre"]')?.focus();
  }

  // Cierra el modal de creación de producto
  function closeCreateModal() {
    if (!createModal) return;
    createModal.classList.remove('is-open');
    createModal.setAttribute('aria-hidden', 'true');
  }

  // Intenta analizar el JSON del atributo data-product de cada fila;
  // devuelve un objeto vacío si el valor es inválido o nulo
  function safeParse(raw) {
    try {
      return JSON.parse(raw || '{}');
    } catch (error) {
      return {};
    }
  }

  // Rellena el formulario de edición con los datos del producto seleccionado
  function fillProductForm(data) {
    if (!productForm || !data) return;

    // Helper interno para asignar el valor a un campo por su atributo name
    const setValue = (name, value) => {
      const field = productForm.querySelector(`[name="${name}"]`);
      if (field) field.value = value ?? '';
    };

    // Asignar cada campo del formulario con los datos del producto
    setValue('product_id', data.codigo || '');
    setValue('codigo_producto', data.codigo || '');
    setValue('nombre', data.nombre || '');
    setValue('descripcion', data.descripcion || '');
    setValue('categoria', data.categoria || '');
    setValue('proveedor', data.proveedor || '');
    setValue('unidad_medida', data.unidad_medida || 'unidad');
    setValue('precio_compra', data.precio_compra || '');
    setValue('precio_venta', data.precio_venta || '');
    setValue('stock_actual', data.stock_actual || '0');
    setValue('stock_minimo', data.stock_minimo || '0');

    // Sincronizar el campo oculto de eliminación y el campo del formulario de movimientos
    if (deleteProductId) deleteProductId.value = data.codigo || '';
    if (movementProductInput) movementProductInput.value = `${data.codigo} | ${data.nombre}`;

    // Marcar como seleccionada la fila correspondiente al producto activo
    rows.forEach((row) => {
      const rowData = safeParse(row.dataset.product);
      row.classList.toggle('is-selected', String(rowData.codigo || '') === String(data.codigo || ''));
    });
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

  // Al hacer clic en una fila, cargar el producto en el formulario
  // y actualizar la URL para reflejar el producto seleccionado
  rows.forEach((row) => {
    row.addEventListener('click', () => {
      const data = safeParse(row.dataset.product);
      fillProductForm(data);
      const url = new URL(window.location.href);
      url.searchParams.set('product', data.codigo || '');
      window.history.replaceState({}, '', url);
    });
  });

  // Escuchar cambios en los controles de filtrado para actualizar la tabla en tiempo real
  searchBox?.addEventListener('input', filterRows);
  categoryFilter?.addEventListener('change', filterRows);

  // Botón para abrir el modal de creación de producto
  document.querySelectorAll('[data-action="new-product"]').forEach((button) => {
    button.addEventListener('click', () => {
      openCreateModal();
    });
  });

  // Botones para cerrar el modal de creación (botón X y fondo oscuro)
  document.querySelectorAll('[data-action="close-create-modal"]').forEach((button) => {
    button.addEventListener('click', closeCreateModal);
  });

  // Cerrar el modal también al presionar la tecla Escape
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeCreateModal();
    }
  });

  // Botón "Editar": desplaza la vista al formulario y coloca el foco en el nombre del producto
  document.querySelectorAll('[data-action="edit-product"]').forEach((button) => {
    button.addEventListener('click', () => {
      productForm?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      productForm?.querySelector('[name="nombre"]')?.focus();
    });
  });

  // Botón "Actualizar stock": desplaza la vista al formulario de movimientos
  document.querySelectorAll('[data-action="focus-movement"]').forEach((button) => {
    button.addEventListener('click', () => {
      document.getElementById('movement-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      movementProductInput?.focus();
    });
  });

  // Si la URL contiene un producto preseleccionado (ej. tras guardar o redirigir),
  // cargar ese producto automáticamente en el formulario al iniciar la página
  const selected = page.dataset.selectedProductId;
  if (selected) {
    const row = rows.find((item) => {
      const data = safeParse(item.dataset.product);
      return String(data.codigo || '') === String(selected);
    });
    if (row) {
      fillProductForm(safeParse(row.dataset.product));
    }
  }

  // Aplicar los filtros iniciales al cargar la página (por si hay parámetros en la URL)
  filterRows();
})();