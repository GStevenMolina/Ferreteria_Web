/**
 * compras.js (módulo Compras)
 *
 * Este script controla el flujo completo del módulo:
 * - Carga proveedores y productos (por proveedor)
 * - Agrega items (producto + cantidad + precio) a una lista
 * - Calcula subtotal, IVA y total en tiempo real
 * - Guarda la compra (POST /compras/nueva/) siempre en NIO
 * - Maneja cambio de moneda VISUAL (NIO <-> USD) usando tasa de cambio manual
 * - Incluye un modal para crear un producto (con proveedor y categoría)
 * - Incluye autocomplete de proveedor dentro del modal
 */
(() => {
  // State global del módulo (en memoria)
  const state = {
    productosMap: new Map(), // cache: id_producto(string) -> {id_producto, nombre, precio_compra, precio_venta, ...}
    items: [],               // items agregados a la compra actual: [{id_producto, nombre, cantidad, precio_unitario, precio_venta}, ...]
    currency: "NIO",         // moneda de visualización (lo que se guarda en BD siempre será NIO)
  };

  // Variables de Autocomplete para proveedor (en modal)
  let provAcSelected = null; // proveedor seleccionado del autocomplete (objeto)
  let provAcTimer = null;    // timer para debounce al escribir
  let provAcLastItems = [];  // últimos resultados mostrados

  // Variables de Autocomplete para categoría (en modal)
  let catAcSelected = null;  // categoría seleccionada del autocomplete (objeto)
  let catAcTimer = null;     // timer para debounce al escribir
  let catAcLastItems = [];   // últimos resultados mostrados

  // Helper para acceder por ID
  function $(id) { return document.getElementById(id); }

  // Helpers de moneda y formato
  function currencySymbol() {
    // Símbolo según moneda actual de visualización
    return state.currency === "USD" ? "$" : "C$";
  }

  function money(n) {
    // Convierte a número y redondea a 2 decimales para mostrar (string con 2 decimales)
    return (Math.round((Number(n) + Number.EPSILON) * 100) / 100).toFixed(2);
  }

  // Tipo de cambio manual (1 USD = X NIO)
  function fxRate() {
    // Lee el input #fx_rate (si existe). Si no es válido, devuelve null.
    const v = parseFloat($("fx_rate")?.value);
    if (!v || isNaN(v) || v <= 0) return null;
    return v;
  }

  function convertAmount(amount, from, to) {
    /**
     * Convierte un monto entre monedas usando el tipo de cambio manual.
     * - NIO -> USD: divide entre la tasa
     * - USD -> NIO: multiplica por la tasa
     */
    if (from === to) return Number(amount);

    const r = fxRate();
    if (!r) throw new Error("Tipo de cambio inválido");

    const n = Number(amount);
    if (!isFinite(n)) return 0;

    if (from === "NIO" && to === "USD") return n / r;
    if (from === "USD" && to === "NIO") return n * r;
    return n;
  }

  function tryConvertAll(toCurrency) {
    /**
     * Convierte TODOS los montos visibles del formulario a otra moneda:
     * - Convierte cada item de state.items (precio_unitario)
     * - Convierte los inputs de precio compra/venta (por si el usuario estaba editando)
     * - Cambia state.currency y re-renderiza
     *
     * Nota: esta conversión es “visual” (estado UI). Al guardar, se envía siempre NIO.
     */
    const fromCurrency = state.currency;
    if (fromCurrency === toCurrency) return;

    // Si vamos a convertir, necesitamos un tipo de cambio válido
    const r = fxRate();
    if (!r) {
      toast("err", "Tipo de cambio", "Ingresa un tipo de cambio válido (USD→NIO).");
      return;
    }

    // 1) Convertir items (esto afecta subtotal/total)
    state.items = state.items.map(it => ({
      ...it,
      precio_unitario: convertAmount(it.precio_unitario, fromCurrency, toCurrency),
    }));

    // 2) Convertir inputs visibles (si contienen algún valor actual)
    $("precio_compra").value = money(convertAmount($("precio_compra").value, fromCurrency, toCurrency));
    $("precio_venta").value = money(convertAmount($("precio_venta").value, fromCurrency, toCurrency));

    // 3) Cambiar moneda actual y re-renderizar UI
    state.currency = toCurrency;
    setCurrencyUI();
    renderTable();
  }

  // Toast (mensajes rápidos)
  function toast(kind, title, body) {
    // kind: "ok" o "err"
    const el = $("toast");
    el.className = "toast " + (kind === "ok" ? "ok" : "err");
    $("toastTitle").textContent = title;
    $("toastBody").textContent = body;
    el.style.display = "block";
    clearTimeout(window.__t);
    window.__t = setTimeout(() => (el.style.display = "none"), 3500);
  }

  // UI: moneda
  function setCurrencyUI() {
    // Actualiza la píldora de moneda
    $("currencyPill").textContent = state.currency === "USD" ? "$ USD" : "C$ NIO";
    renderTable(); // recalcular tabla/totales con símbolo actualizado
  }

  // Cálculo de IVA y totales
  function getIvaRate() {
    // El usuario ingresa el IVA como % (por ejemplo "15"). Aquí lo convertimos a factor (0.15)
    const v = parseFloat($("iva_rate").value);
    if (isNaN(v) || v < 0) return 0;
    return v / 100;
  }

  function calc() {
    // subtotal = sum(cantidad * precio_unitario)
    const subtotal = state.items.reduce((a, it) => a + it.cantidad * it.precio_unitario, 0);
    const impuesto = subtotal * getIvaRate();
    const total = subtotal + impuesto;

    // Mostrar en UI usando símbolo de moneda actual
    const s = currencySymbol();
    $("sub").textContent = s + money(subtotal);
    $("tax").textContent = s + money(impuesto);
    $("tot").textContent = s + money(total);
  }

  // Render de tabla de items
  function renderTable() {
    const tbody = $("tbody");
    const s = currencySymbol();

    // Caso base: sin items
    if (state.items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="note">No hay items todavía.</td></tr>`;
      calc();
      return;
    }

    // Render de cada fila
    tbody.innerHTML = state.items.map((it, idx) => {
      const sub = it.cantidad * it.precio_unitario;
      return `
        <tr>
          <td>${it.nombre}</td>
          <td class="right">${it.cantidad}</td>
          <td class="right">${s}${money(it.precio_unitario)}</td>
          <td class="right">${s}${money(sub)}</td>
          <td class="right">
            <button class="btn-danger" type="button" data-remove="${idx}">Eliminar</button>
          </td>
        </tr>`;
    }).join("");

    // Bind de “Eliminar” por fila
    tbody.querySelectorAll("button[data-remove]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.getAttribute("data-remove"), 10);
        state.items.splice(idx, 1);
        renderTable();
      });
    });

    calc();
  }

  function syncSelectedProductCache() {
    const idProducto = $("producto")?.value;
    if (!idProducto) return;

    const p = state.productosMap.get(String(idProducto));
    if (!p) return;

    p.precio_compra = Number($("precio_compra")?.value || 0);
    p.precio_venta = Number($("precio_venta")?.value || 0);
  }

  // CSRF y helpers de POST (Django)
  function getCsrf() {
    // Obtiene el token CSRF del formulario oculto #csrfForm
    const el = document.querySelector("#csrfForm input[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  async function postForm(url, data) {
    /**
     * Helper para POST a endpoints que reciben form-data (request.POST).
     * Retorna { r, j }:
     * - r: Response
     * - j: JSON parseado (si se pudo)
     */
    const csrfToken = getCsrf();
    const form = new FormData();
    Object.entries(data).forEach(([k, v]) => form.append(k, v ?? ""));
    const r = await fetch(url, { method: "POST", headers: { "X-CSRFToken": csrfToken }, body: form });
    const j = await r.json().catch(() => ({}));
    return { r, j };
  }

  // Carga de proveedores y productos
  async function loadProveedores() {
    // GET /compras/api/proveedores/ => llena el select #proveedor
    const r = await fetch("/compras/api/proveedores/");
    const j = await r.json().catch(() => ({}));
    const sel = $("proveedor");

    if (!r.ok || !j.data) {
      sel.innerHTML = `<option value="">— Error cargando proveedores —</option>`;
      return;
    }

    sel.innerHTML =
      `<option value="">— Selecciona proveedor —</option>` +
      j.data.map((p) => `<option value="${p.id_proveedor}">${p.nombre}</option>`).join("");
  }

  async function loadProductosByProveedor(id_proveedor) {
    /**
     * Carga productos del proveedor seleccionado:
     * - limpia el cache productosMap
     * - llena el select #producto
     */
    const sel = $("producto");
    sel.innerHTML = `<option value="">Cargando productos...</option>`;
    state.productosMap.clear();

    const r = await fetch("/compras/api/productos/?id_proveedor=" + encodeURIComponent(id_proveedor));
    const j = await r.json().catch(() => ({}));

    if (!r.ok || !j.ok) {
      sel.innerHTML = `<option value="">— Error cargando productos —</option>`;
      toast("err", "Productos", j.error || "No se pudieron cargar.");
      return;
    }

    // cache en memoria: id -> objeto producto
    j.data.forEach((p) => state.productosMap.set(String(p.id_producto), p));

    // llenar dropdown
    sel.innerHTML =
      `<option value="">— Selecciona —</option>` +
      j.data.map((p) => `<option value="${p.id_producto}">${p.nombre}</option>`).join("");
  }

  // Modal: forzar que el modal sea hijo directo de <body>
  // (evita problemas de overflow/posición)
  function mountModalToBody() {
    const modal = $("modalNuevoProducto");
    if (!modal) return;
    if (modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }
  }

  // Modal: bloqueo/desbloqueo campos de proveedor
  // - Si seleccionas un proveedor del autocomplete, bloquea campos para evitar editarlo sin querer
  // - Si escribes manual, quedan editables (para proveedor nuevo)
  function setProveedorFieldsLocked(locked) {
    const ids = [
      "np_prov_telefono",
      "np_prov_email",
      "np_prov_contacto",
      "np_prov_direccion",
      "np_prov_tipo",
    ];
    ids.forEach((id) => {
      const el = $(id);
      if (!el) return;
      el.readOnly = !!locked;
      el.style.opacity = locked ? "0.85" : "";
    });
  }

  function setCategoriaFieldsLocked(locked) {
    const el = $("np_cat_desc");
    if (!el) return;
    el.readOnly = !!locked;
    el.style.opacity = locked ? "0.85" : "";
  }

  function fillProveedorFields(p) {
    // Copia los datos del proveedor seleccionado hacia los inputs del modal
    $("np_prov_nombre").value = p.nombre || "";
    $("np_prov_telefono").value = p.telefono || "";
    $("np_prov_email").value = p.email || "";
    $("np_prov_contacto").value = p.numero_contacto || "";
    $("np_prov_direccion").value = p.direccion || "";
    $("np_prov_tipo").value = p.tipo_proveedor || "";
  }

  // Autocomplete: mostrar/ocultar lista y manejar selección
  function hideProvList() {
    const list = $("provAcList");
    if (!list) return;
    list.style.display = "none";
    list.innerHTML = "";
  }

  function hideCatList() {
    const list = $("catAcList");
    if (!list) return;
    list.style.display = "none";
    list.innerHTML = "";
  }

  function showProvList(items) {
    const list = $("provAcList");
    if (!list) return;

    provAcLastItems = Array.isArray(items) ? items : [];

    if (provAcLastItems.length === 0) {
      hideProvList();
      return;
    }

    // Render de resultados (cada item clickable)
    list.innerHTML = provAcLastItems.map(p => `
      <div class="ac__item" data-id="${p.id_proveedor}">
        <div><b>${p.nombre}</b></div>
        <div class="ac__muted">${(p.telefono || "")}${p.email ? " • " + p.email : ""}</div>
      </div>
    `).join("");

    list.style.display = "block";

    // Bind click para seleccionar proveedor existente
    list.querySelectorAll(".ac__item").forEach(el => {
      el.addEventListener("click", () => {
        const id = Number(el.getAttribute("data-id"));
        const p = provAcLastItems.find(x => Number(x.id_proveedor) === id);
        if (!p) return;

        provAcSelected = p;
        fillProveedorFields(p);
        setProveedorFieldsLocked(true);
        hideProvList();
      });
    });
  }

  function showCatList(items) {
    const list = $("catAcList");
    if (!list) return;

    catAcLastItems = Array.isArray(items) ? items : [];

    if (catAcLastItems.length === 0) {
      hideCatList();
      return;
    }

    list.innerHTML = catAcLastItems.map(c => `
      <div class="ac__item" data-id="${c.id_categoria}">
        <div><b>${c.nombre}</b></div>
        <div class="ac__muted">${c.descripcion || "Sin descripción"}</div>
      </div>
    `).join("");

    list.style.display = "block";

    list.querySelectorAll(".ac__item").forEach(el => {
      el.addEventListener("click", () => {
        const id = Number(el.getAttribute("data-id"));
        const c = catAcLastItems.find(x => Number(x.id_categoria) === id);
        if (!c) return;

        catAcSelected = c;
        $("np_cat_nombre").value = c.nombre || "";
        $("np_cat_desc").value = c.descripcion || "";
        setCategoriaFieldsLocked(true);
        hideCatList();
      });
    });
  }

  async function searchProveedores(q) {
    // GET /compras/api/proveedores/buscar/?q=... (autocomplete)
    const r = await fetch("/compras/api/proveedores/buscar/?q=" + encodeURIComponent(q));
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.ok) return [];
    return j.data || [];
  }

  async function searchCategorias(q) {
    // GET /compras/api/categorias/buscar/?q=... (autocomplete)
    const r = await fetch("/compras/api/categorias/buscar/?q=" + encodeURIComponent(q));
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.ok) return [];
    return j.data || [];
  }

  // Modal: limpiar / abrir / cerrar
  function clearNuevoProductoForm() {
    // Limpia inputs de Proveedor
    if ($("np_prov_nombre")) $("np_prov_nombre").value = "";
    if ($("np_prov_telefono")) $("np_prov_telefono").value = "";
    if ($("np_prov_email")) $("np_prov_email").value = "";
    if ($("np_prov_contacto")) $("np_prov_contacto").value = "";
    if ($("np_prov_direccion")) $("np_prov_direccion").value = "";
    if ($("np_prov_tipo")) $("np_prov_tipo").value = "";

    // Limpia inputs de Producto
    if ($("np_prod_nombre")) $("np_prod_nombre").value = "";
    if ($("np_prod_desc")) $("np_prod_desc").value = "";
    if ($("np_prod_pc")) $("np_prod_pc").value = "0.00";
    if ($("np_prod_pv")) $("np_prod_pv").value = "0.00";
    if ($("np_prod_um")) $("np_prod_um").value = "";

    // Limpia inputs de Categoría
    if ($("np_cat_nombre")) $("np_cat_nombre").value = "";
    if ($("np_cat_desc")) $("np_cat_desc").value = "";

    // Estado del autocomplete
    provAcSelected = null;
    hideProvList();
    catAcSelected = null;
    hideCatList();

    // Campos editables por defecto (para proveedor nuevo)
    setProveedorFieldsLocked(false);
    setCategoriaFieldsLocked(false);
  }

  function openNuevoProducto() {
    // Asegura que el modal sea hijo de body y lo prepara limpio
    mountModalToBody();
    clearNuevoProductoForm();

    // Mostrar modal + bloquear scroll del body
    document.body.style.overflow = "hidden";
    $("modalNuevoProducto").style.display = "flex";

    // Si ya hay proveedor seleccionado en el formulario principal,
    // pre-rellena el input del modal y dispara búsqueda para facilitar selección
    const idProvMain = $("proveedor")?.value;
    if (idProvMain) {
      const opt = $("proveedor").querySelector(`option[value="${idProvMain}"]`);
      if (opt && opt.textContent) {
        $("np_prov_nombre").value = opt.textContent.trim();
        provAcSelected = null;
        $("np_prov_nombre").dispatchEvent(new Event("input"));
      }
    }
  }

  function closeNuevoProducto() {
    // Ocultar modal + restaurar scroll del body y limpiar formulario
    $("modalNuevoProducto").style.display = "none";
    document.body.style.overflow = "";
    hideProvList();
    clearNuevoProductoForm();
  }

  async function bootstrapNuevoProductoFromQuery() {
    const qs = new URLSearchParams(window.location.search);
    const shouldOpen = qs.get("open_np") === "1";
    if (!shouldOpen) return;

    const idProveedor = (qs.get("id_proveedor") || "").trim();
    const nombreProveedor = (qs.get("proveedor") || "").trim();

    if (idProveedor) {
      const selProv = $("proveedor");

      if (selProv && !selProv.querySelector(`option[value="${idProveedor}"]`) && nombreProveedor) {
        const opt = document.createElement("option");
        opt.value = idProveedor;
        opt.textContent = nombreProveedor;
        selProv.appendChild(opt);
      }

      if (selProv) selProv.value = idProveedor;
      await loadProductosByProveedor(idProveedor);
    }

    openNuevoProducto();

    // Limpia query params para no reabrir el modal al recargar
    window.history.replaceState({}, "", window.location.pathname);
  }

  // Modal: Guardar proveedor/categoría/producto (secuencia de POST)
  async function guardarNuevoProducto() {
    // Construir payloads desde inputs
    const prov = {
      nombre: $("np_prov_nombre").value,
      telefono: $("np_prov_telefono").value,
      email: $("np_prov_email").value,
      numero_contacto: $("np_prov_contacto").value,
      direccion: $("np_prov_direccion").value,
      tipo_proveedor: $("np_prov_tipo").value,
    };

    const cat = {
      nombre: $("np_cat_nombre").value,
      descripcion: $("np_cat_desc").value,
    };

    const prod = {
      nombre: $("np_prod_nombre").value,
      descripcion: $("np_prod_desc").value,
      precio_compra: $("np_prod_pc").value,
      precio_venta: $("np_prod_pv").value,
      unidad_medida: $("np_prod_um").value,
    };

    // Validaciones rápidas de frontend
    if (!prov.nombre.trim()) return toast("err", "Proveedor", "Nombre de proveedor requerido.");
    if (!cat.nombre.trim()) return toast("err", "Categoría", "Nombre de categoría requerido.");
    if (!prod.nombre.trim()) return toast("err", "Producto", "Nombre de producto requerido.");

    const btn = $("btnGuardarNuevoProducto");
    btn.disabled = true;

    try {
      // 1) upsert proveedor (crea o reutiliza)
      const a = await postForm("/compras/api/proveedor/upsert/", prov);
      if (!a.r.ok || !a.j.ok) return toast("err", "Proveedor", a.j.error || "Error al guardar proveedor.");
      const id_proveedor = a.j.data.id_proveedor;

      // 2) upsert categoría (crea o reutiliza)
      const b = await postForm("/compras/api/categoria/upsert/", cat);
      if (!b.r.ok || !b.j.ok) return toast("err", "Categoría", b.j.error || "Error al guardar categoría.");
      const id_categoria = b.j.data.id_categoria;

      // 3) crear producto (asociado a proveedor y categoría)
      const c = await postForm("/compras/api/producto/crear/", { id_proveedor, id_categoria, ...prod });
      if (!c.r.ok || !c.j.ok) return toast("err", "Producto", c.j.error || "Error al crear producto.");

      const newProd = c.j.data;

      // 4) cerrar modal
      closeNuevoProducto();

      // 5) refrescar proveedores en el select principal (para que aparezca el nuevo si se creó)
      await loadProveedores();

      // 6) si por alguna razón no existiera el option, lo agregamos manualmente
      const selProv = $("proveedor");
      const idStr = String(id_proveedor);
      if (selProv && !selProv.querySelector(`option[value="${idStr}"]`)) {
        const opt = document.createElement("option");
        opt.value = idStr;
        opt.textContent = prov.nombre.trim();
        selProv.appendChild(opt);
      }

      // 7) seleccionar proveedor (sin disparar change para no borrar items existentes)
      $("proveedor").value = idStr;

      // 8) preparar cantidad (sin limpiar items ya agregados)
      $("cantidad").value = "1";

      // 9) cargar productos y seleccionar el nuevo
      await loadProductosByProveedor(idStr);
      $("producto").value = String(newProd.id_producto);

      // 10) rellenar precios del producto nuevo
      $("precio_compra").value = Number(newProd.precio_compra || 0).toFixed(2);
      $("precio_venta").value = Number(newProd.precio_venta || 0).toFixed(2);

      toast("ok", "Producto creado", `Se creó "${newProd.nombre}" y ya está listo para agregar a la compra.`);
    } catch (e) {
      toast("err", "Error", "Error de red/servidor.");
    } finally {
      btn.disabled = false;
    }
  }

  // Bind de eventos de la UI principal
  function bindEvents() {
    // Toggle moneda: convierte montos usando tipo de cambio manual
    $("btnToggleCurrency").addEventListener("click", () => {
      const next = state.currency === "NIO" ? "USD" : "NIO";
      tryConvertAll(next);
    });

    // Recalcular totales cuando cambie IVA
    $("iva_rate").addEventListener("input", calc);

    // Cambio de proveedor:
    // - limpia items porque cambia el contexto de compra
    // - recarga productos del proveedor
    $("proveedor").addEventListener("change", (e) => {
      const id_proveedor = e.target.value;

      state.items = [];
      renderTable();

      $("precio_compra").value = "0.00";
      $("precio_venta").value = "0.00";
      $("cantidad").value = "1";

      if (!id_proveedor) {
        $("producto").innerHTML = `<option value="">— Selecciona proveedor primero —</option>`;
        return;
      }
      loadProductosByProveedor(id_proveedor);
    });

    // Cambio de producto:
    // - lee el producto desde productosMap
    // - rellena inputs de precios
    $("producto").addEventListener("change", (e) => {
      const p = state.productosMap.get(String(e.target.value));
      if (!p) return;
      $("precio_compra").value = Number(p.precio_compra || 0).toFixed(2);
      $("precio_venta").value = Number(p.precio_venta || 0).toFixed(2);
    });

    $("precio_compra").addEventListener("input", syncSelectedProductCache);
    $("precio_venta").addEventListener("input", syncSelectedProductCache);

    // Agregar item a la lista
    $("btnAdd").addEventListener("click", () => {
      const id_producto = $("producto").value;
      const p = state.productosMap.get(String(id_producto));
      const cantidad = parseInt($("cantidad").value, 10);
      const precio_unitario = parseFloat($("precio_compra").value);
      const precio_venta = parseFloat($("precio_venta").value);

      if (!p) return toast("err", "Falta producto", "Selecciona un producto.");
      if (!cantidad || cantidad <= 0) return toast("err", "Cantidad inválida", "La cantidad debe ser mayor que 0.");
      if (isNaN(precio_unitario) || precio_unitario < 0)
        return toast("err", "Precio inválido", "Revisa el precio de compra.");
      if (isNaN(precio_venta) || precio_venta < 0)
        return toast("err", "Precio inválido", "Revisa el precio de venta.");

      // Si ya existe en la lista:
      // - suma cantidad
      // - reemplaza precio_unitario por el más reciente (último editado)
      const existing = state.items.find((x) => String(x.id_producto) === String(id_producto));
      if (existing) {
        existing.cantidad += cantidad;
        existing.precio_unitario = precio_unitario;
        existing.precio_venta = precio_venta;
      } else {
        state.items.push({ id_producto: p.id_producto, nombre: p.nombre, cantidad, precio_unitario, precio_venta });
      }

      renderTable();
      $("cantidad").value = "1";
    });

    // Guardar compra (POST)
    $("btnSave").addEventListener("click", async () => {
      const id_proveedor = $("proveedor").value;
      if (!id_proveedor) return toast("err", "Falta proveedor", "Selecciona un proveedor.");
      if (state.items.length === 0) return toast("err", "Sin items", "Agrega al menos un producto.");

      const ivaRate = parseFloat($("iva_rate").value);
      if (isNaN(ivaRate) || ivaRate < 0 || ivaRate > 100)
        return toast("err", "IVA inválido", "IVA debe estar entre 0 y 100.");

      const csrfToken = getCsrf();

      // Guardar SIEMPRE en NIO:
      // - Si la UI está en USD, convertimos antes de enviar
      let itemsToSend = state.items;

      if (state.currency === "USD") {
        const r = fxRate();
        if (!r) return toast("err", "Tipo de cambio", "Ingresa un tipo de cambio válido para guardar en C$.");

        itemsToSend = state.items.map(it => ({
          ...it,
          precio_unitario: convertAmount(it.precio_unitario, "USD", "NIO"),
        }));
      }

      const form = new FormData();
      form.append("id_proveedor", id_proveedor);
      form.append("iva_rate", $("iva_rate").value);

      // Enviar items como JSON string
      form.append("items", JSON.stringify(itemsToSend.map((it) => ({
        id_producto: it.id_producto,
        cantidad: it.cantidad,
        precio_unitario: money(it.precio_unitario),
        precio_venta: money(it.precio_venta ?? 0),
      }))));

      const btn = $("btnSave");
      btn.disabled = true;

      try {
        const r = await fetch("/compras/nueva/", { method: "POST", headers: { "X-CSRFToken": csrfToken }, body: form });
        const j = await r.json().catch(() => ({}));
        if (!r.ok || !j.ok) return toast("err", "No se pudo guardar", j.error || "Error en servidor.");

        toast("ok", "Compra guardada",
          `Compra #${j.id_compra}. Factura ${j.numero_factura}. IVA ${j.iva_rate}%. Total C$${j.total}.`
        );

        // Reset UI de compra
        state.items = [];
        renderTable();
        $("producto").innerHTML = `<option value="">— Selecciona proveedor primero —</option>`;
        $("precio_compra").value = "0.00";
        $("precio_venta").value = "0.00";
        $("cantidad").value = "1";
        $("proveedor").value = "";

        // Volver a NIO visualmente (opcional)
        state.currency = "NIO";
        setCurrencyUI();
      } catch (e) {
        toast("err", "Error", "Error de red o servidor.");
      } finally {
        btn.disabled = false;
      }
    });

    // Modal: open/close
    $("btnNuevoProducto").addEventListener("click", openNuevoProducto);
    $("btnCloseModalNP").addEventListener("click", closeNuevoProducto);
    $("modalBackdrop").addEventListener("click", closeNuevoProducto);
    $("btnGuardarNuevoProducto").addEventListener("click", guardarNuevoProducto);

    // Autocomplete proveedor: input handler con debounce
    if ($("np_prov_nombre")) {
      $("np_prov_nombre").setAttribute("autocomplete", "off");

      $("np_prov_nombre").addEventListener("input", () => {
        const q = $("np_prov_nombre").value.trim();

        // Si el usuario escribe, asumimos proveedor nuevo hasta que seleccione uno
        provAcSelected = null;
        setProveedorFieldsLocked(false);

        if (!q) {
          hideProvList();
          return;
        }

        // Debounce para no consultar en cada tecla
        clearTimeout(provAcTimer);
        provAcTimer = setTimeout(async () => {
          const items = await searchProveedores(q);
          showProvList(items);
        }, 180);
      });
    }

    if ($("np_cat_nombre")) {
      $("np_cat_nombre").setAttribute("autocomplete", "off");

      $("np_cat_nombre").addEventListener("input", () => {
        const q = $("np_cat_nombre").value.trim();

        catAcSelected = null;
        setCategoriaFieldsLocked(false);

        if (!q) {
          hideCatList();
          return;
        }

        clearTimeout(catAcTimer);
        catAcTimer = setTimeout(async () => {
          const items = await searchCategorias(q);
          showCatList(items);
        }, 180);
      });
    }

    // Click fuera del wrapper para cerrar lista del autocomplete
    document.addEventListener("click", (e) => {
      const wrap = $("provAcWrap");
      if (!wrap) return;
      if (!wrap.contains(e.target)) hideProvList();

      const catWrap = $("catAcWrap");
      if (catWrap && !catWrap.contains(e.target)) hideCatList();
    });

    // ESC cierra el modal si está abierto
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && $("modalNuevoProducto")?.style.display === "flex") {
        closeNuevoProducto();
      }
    });
  }

  // Init del módulo
  document.addEventListener("DOMContentLoaded", async () => {
    mountModalToBody();
    bindEvents();
    await loadProveedores();
    await bootstrapNuevoProductoFromQuery();
    setCurrencyUI();
    renderTable();
  });
})();