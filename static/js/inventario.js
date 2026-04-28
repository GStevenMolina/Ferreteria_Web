(function () {
  const page = document.querySelector('.inventory-page');
  if (!page) return;

  const searchBox = document.getElementById('searchBox');
  const categoryFilter = document.getElementById('categoryFilter');
  const rows = Array.from(document.querySelectorAll('.inventory-row'));
  const productForm = document.getElementById('product-form');
  const createModal = document.getElementById('createProductModal');
  const createForm = document.getElementById('create-product-form');
  const movementProductInput = document.getElementById('movementProductInput');
  const deleteProductId = document.getElementById('deleteProductId');

  function openCreateModal() {
    if (!createModal) return;
    createModal.classList.add('is-open');
    createModal.setAttribute('aria-hidden', 'false');
    createForm?.reset();
    createForm?.querySelector('[name="nombre"]')?.focus();
  }

  function closeCreateModal() {
    if (!createModal) return;
    createModal.classList.remove('is-open');
    createModal.setAttribute('aria-hidden', 'true');
  }

  function safeParse(raw) {
    try {
      return JSON.parse(raw || '{}');
    } catch (error) {
      return {};
    }
  }

  function fillProductForm(data) {
    if (!productForm || !data) return;
    const setValue = (name, value) => {
      const field = productForm.querySelector(`[name="${name}"]`);
      if (field) field.value = value ?? '';
    };

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

    if (deleteProductId) deleteProductId.value = data.codigo || '';
    if (movementProductInput) movementProductInput.value = `${data.codigo} | ${data.nombre}`;

    rows.forEach((row) => {
      const rowData = safeParse(row.dataset.product);
      row.classList.toggle('is-selected', String(rowData.codigo || '') === String(data.codigo || ''));
    });
  }

  function filterRows() {
    const term = (searchBox?.value || '').toLowerCase().trim();
    const category = categoryFilter?.value || '';

    rows.forEach((row) => {
      const data = safeParse(row.dataset.product);
      const matchesCategory = !category || String(data.categoria || '') === String(category);
      const haystack = [data.codigo, data.nombre].join(' ').toLowerCase();
      const matchesTerm = !term || haystack.includes(term);
      row.style.display = matchesCategory && matchesTerm ? '' : 'none';
    });
  }

  rows.forEach((row) => {
    row.addEventListener('click', () => {
      const data = safeParse(row.dataset.product);
      fillProductForm(data);
      const url = new URL(window.location.href);
      url.searchParams.set('product', data.codigo || '');
      window.history.replaceState({}, '', url);
    });
  });

  searchBox?.addEventListener('input', filterRows);
  categoryFilter?.addEventListener('change', filterRows);

  document.querySelectorAll('[data-action="new-product"]').forEach((button) => {
    button.addEventListener('click', () => {
      openCreateModal();
    });
  });

  document.querySelectorAll('[data-action="close-create-modal"]').forEach((button) => {
    button.addEventListener('click', closeCreateModal);
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeCreateModal();
    }
  });

  document.querySelectorAll('[data-action="edit-product"]').forEach((button) => {
    button.addEventListener('click', () => {
      productForm?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      productForm?.querySelector('[name="nombre"]')?.focus();
    });
  });

  document.querySelectorAll('[data-action="focus-movement"]').forEach((button) => {
    button.addEventListener('click', () => {
      document.getElementById('movement-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      movementProductInput?.focus();
    });
  });

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

  filterRows();
})();