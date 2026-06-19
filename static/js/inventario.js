// Módulo de Inventario - Ventana Flotante y Filtros Unificado
(function () {
  // Auxiliar para obtener el token CSRF obligatorio de Django
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === name + '=') {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  function safeParseGlobal(raw) {
    try { return JSON.parse(raw || '{}'); } catch (e) { return {}; }
  }

  // Elementos del DOM del Modal definidos correctamente al inicio del ciclo de vida
  const quickModal = document.getElementById('quickEditModal');
  const quickEditForm = document.getElementById('quickEditForm');
  const closeModalBtn = document.getElementById('closeModalBtn');
  const searchBox = document.getElementById('searchBox');

  // =========================================================================
  // 🪐 CONTROL GLOBAL DE LA VENTANA FLOTANTE (ABRIR Y CERRAR)
  // =========================================================================
  
  window.openQuickModal = function(row) {
    if (!quickModal) return;
    
    quickModal._currentRow = row;
    const productData = safeParseGlobal(row.dataset.product);

    // Captura de todos los inputs ampliados
    const quickId = document.getElementById('modalProductId');
    const quickNombre = document.getElementById('modalProductName');
    const quickCategory = document.getElementById('modalProductCategory');
    const quickProvider = document.getElementById('modalProductProvider');
    const quickUnit = document.getElementById('modalProductUnit');
    const quickStatus = document.getElementById('modalProductStatus');
    const quickCostPrice = document.getElementById('modalProductCostPrice');
    const quickPrecio = document.getElementById('modalProductPrice');
    const quickStock = document.getElementById('modalProductStock');
    const quickStockMin = document.getElementById('modalProductMinStock');

    // Inyección fluida de datos de forma segura utilizando el JSON del Backend
    if (quickId) quickId.value = productData.id_producto || "";
    if (quickNombre) quickNombre.value = productData.nombre || "";
    if (quickCategory) quickCategory.value = productData.id_categoria || "";
    if (quickProvider) quickProvider.value = productData.id_provider || productData.id_proveedor || "";
    if (quickUnit) quickUnit.value = productData.unidad_medida || "Unidad";
    if (quickStatus) quickStatus.value = productData.estado || "Activo";
    if (quickCostPrice) quickCostPrice.value = productData.precio_compra || 0;
    if (quickPrecio) quickPrecio.value = productData.precio_venta || 0;
    
    // 🔥 Sincronización directa del Stock Físico y Mínimo
    if (quickStock) quickStock.value = productData.stock_actual !== undefined ? productData.stock_actual : 0;
    if (quickStockMin) quickStockMin.value = productData.stock_minimo !== undefined ? productData.stock_minimo : 0;

    quickModal.classList.add('is-open');
  };

  window.closeQuickModal = function() {
    if (quickModal) {
      quickModal.classList.remove('is-open');
      quickModal._currentRow = null;
    }
    if (quickEditForm) {
      quickEditForm.reset();
    }
  };

  // =========================================================================
  // 🔍 ASIGNACIÓN DE EVENTOS ASÍNCRONOS
  // =========================================================================

  // Evento para el botón de cerrar (X)
  if (closeModalBtn) {
    closeModalBtn.addEventListener('click', function(e) {
      e.preventDefault();
      window.closeQuickModal();
    });
  }

  // Cerrar al hacer clic en el fondo oscuro
  if (quickModal) {
    quickModal.addEventListener('click', function (e) {
      if (e.target === quickModal) {
        window.closeQuickModal();
      }
    });
  }

  // Envío asíncrono del formulario extendido mediante Fetch API
  if (quickEditForm) {
    quickEditForm.addEventListener('submit', function (e) {
      e.preventDefault();

      const payload = {
        id_producto: document.getElementById('modalProductId').value,
        nombre: document.getElementById('modalProductName').value.trim(),
        id_categoria: document.getElementById('modalProductCategory').value,
        id_proveedor: document.getElementById('modalProductProvider').value,
        unidad_medida: document.getElementById('modalProductUnit').value,
        estado: document.getElementById('modalProductStatus').value,
        precio_compra: parseFloat(document.getElementById('modalProductCostPrice').value) || 0,
        precio_venta: parseFloat(document.getElementById('modalProductPrice').value) || 0,
        stock_actual: parseInt(document.getElementById('modalProductStock').value, 10) || 0,
        stock_minimo: parseInt(document.getElementById('modalProductMinStock').value, 10) || 0
      };

      fetch('/registro/api/quick_update/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
        },
        body: JSON.stringify(payload),
      })
      .then((r) => {
        if (!r.ok) throw new Error('Error en el servidor');
        return r.json();
      })
      .then((json) => {
        if (json && json.ok) {
          window.closeQuickModal();
          window.location.reload(); // Recarga limpia para recalcular los KPIs e insignias
        } else {
          alert('Error: ' + (json.error || 'No se pudo guardar la información'));
        }
      })
      .catch((err) => {
        console.error(err);
        alert('Error de comunicación con el servidor.');
      });
    });
  }

  // Autocompletado en tiempo real de búsqueda
  if (searchBox) {
    const url = searchBox.dataset.autocompleteUrl;
    const datalist = document.getElementById('search-suggestions');

    searchBox.addEventListener('input', function () {
      const q = this.value.trim();
      if (q.length < 2) {
        if (datalist) datalist.innerHTML = '';
        return;
      }

      fetch(`${url}?q=${encodeURIComponent(q)}`)
        .then((res) => res.json())
        .then((data) => {
          if (datalist && Array.isArray(data.results)) {
            datalist.innerHTML = data.results
              .map((item) => `<option value="${item.nombre}"></option>`)
              .join('');
          }
        })
        .catch((err) => console.error('Error en sugerencias:', err));
    });
  }
})();