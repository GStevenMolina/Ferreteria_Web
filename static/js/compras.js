(() => {
  const state = {
    productosMap: new Map(),
    items: [],
    currency: "NIO", // Moneda de visualización (lo guardado SIEMPRE será NIO)
  };

  // ===== Autocomplete proveedor =====
  let provAcSelected = null; // objeto proveedor seleccionado del autocomplete
  let provAcTimer = null;
  let provAcLastItems = [];

  function $(id) { return document.getElementById(id); }

  function currencySymbol() {
    return state.currency === "USD" ? "$" : "C$";
  }

  function money(n) {
    return (Math.round((Number(n) + Number.EPSILON) * 100) / 100).toFixed(2);
  }

  // ============================================================
  // Tipo de cambio manual (1 USD = X NIO)
  // ============================================================
  function fxRate() {
    const v = parseFloat($("fx_rate")?.value);
    if (!v || isNaN(v) || v <= 0) return null;
    return v;
  }

  function convertAmount(amount, from, to) {
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
    const fromCurrency = state.currency;
    if (fromCurrency === toCurrency) return;

    // Requiere TC si hay conversión
    const r = fxRate();
    if (!r) {
      toast("err", "Tipo de cambio", "Ingresa un tipo de cambio válido (USD→NIO).");
      return;
    }

    // Convertir items (esto hace que totales cambien también)
    state.items = state.items.map(it => ({
      ...it,
      precio_unitario: convertAmount(it.precio_unitario, fromCurrency, toCurrency),
    }));

    // Convertir inputs visibles (por si el usuario estaba editando)
    $("precio_compra").value = money(convertAmount($("precio_compra").value, fromCurrency, toCurrency));
    $("precio_venta").value = money(convertAmount($("precio_venta").value, fromCurrency, toCurrency));

    state.currency = toCurrency;
    setCurrencyUI();
    renderTable();
  }

  // ============================================================
  // UI helpers
  // ============================================================
  function toast(kind, title, body) {
    const el = $("toast");
    el.className = "toast " + (kind === "ok" ? "ok" : "err");
    $("toastTitle").textContent = title;
    $("toastBody").textContent = body;
    el.style.display = "block";
    clearTimeout(window.__t);
    window.__t = setTimeout(() => (el.style.display = "none"), 3500);
  }

  function setCurrencyUI() {
    $("currencyPill").textContent = state.currency === "USD" ? "$ USD" : "C$ NIO";
    renderTable();
  }

  function getIvaRate() {
    const v = parseFloat($("iva_rate").value);
    if (isNaN(v) || v < 0) return 0;
    return v / 100;
  }

  function calc() {
    const subtotal = state.items.reduce((a, it) => a + it.cantidad * it.precio_unitario, 0);
    const impuesto = subtotal * getIvaRate();
    const total = subtotal + impuesto;

    const s = currencySymbol();
    $("sub").textContent = s + money(subtotal);
    $("tax").textContent = s + money(impuesto);
    $("tot").textContent = s + money(total);
  }

  function renderTable() {
    const tbody = $("tbody");
    const s = currencySymbol();

    if (state.items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="note">No hay items todavía.</td></tr>`;
      calc();
      return;
    }

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

    tbody.querySelectorAll("button[data-remove]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.getAttribute("data-remove"), 10);
        state.items.splice(idx, 1);
        renderTable();
      });
    });

    calc();
  }

  function getCsrf() {
    const el = document.querySelector("#csrfForm input[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  async function postForm(url, data) {
    const csrfToken = getCsrf();
    const form = new FormData();
    Object.entries(data).forEach(([k, v]) => form.append(k, v ?? ""));
    const r = await fetch(url, { method: "POST", headers: { "X-CSRFToken": csrfToken }, body: form });
    const j = await r.json().catch(() => ({}));
    return { r, j };
  }

  async function loadProveedores() {
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

    j.data.forEach((p) => state.productosMap.set(String(p.id_producto), p));
    sel.innerHTML =
      `<option value="">— Selecciona —</option>` +
      j.data.map((p) => `<option value="${p.id_producto}">${p.nombre}</option>`).join("");
  }

  // ============ Modal: FORZAR A QUE SEA HIJO DIRECTO DE <body> ============
  function mountModalToBody() {
    const modal = $("modalNuevoProducto");
    if (!modal) return;
    if (modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }
  }

  // ===== Bloqueo / desbloqueo campos proveedor =====
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

  // ===== Autocomplete helpers =====
  function fillProveedorFields(p) {
    $("np_prov_nombre").value = p.nombre || "";
    $("np_prov_telefono").value = p.telefono || "";
    $("np_prov_email").value = p.email || "";
    $("np_prov_contacto").value = p.numero_contacto || "";
    $("np_prov_direccion").value = p.direccion || "";
    $("np_prov_tipo").value = p.tipo_proveedor || "";
  }

  function hideProvList() {
    const list = $("provAcList");
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

    list.innerHTML = provAcLastItems.map(p => `
      <div class="ac__item" data-id="${p.id_proveedor}">
        <div><b>${p.nombre}</b></div>
        <div class="ac__muted">${(p.telefono || "")}${p.email ? " • " + p.email : ""}</div>
      </div>
    `).join("");

    list.style.display = "block";

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

  async function searchProveedores(q) {
    const r = await fetch("/compras/api/proveedores/buscar/?q=" + encodeURIComponent(q));
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.ok) return [];
    return j.data || [];
  }

  function clearNuevoProductoForm() {
    // Proveedor
    if ($("np_prov_nombre")) $("np_prov_nombre").value = "";
    if ($("np_prov_telefono")) $("np_prov_telefono").value = "";
    if ($("np_prov_email")) $("np_prov_email").value = "";
    if ($("np_prov_contacto")) $("np_prov_contacto").value = "";
    if ($("np_prov_direccion")) $("np_prov_direccion").value = "";
    if ($("np_prov_tipo")) $("np_prov_tipo").value = "";

    // Producto
    if ($("np_prod_nombre")) $("np_prod_nombre").value = "";
    if ($("np_prod_desc")) $("np_prod_desc").value = "";
    if ($("np_prod_pc")) $("np_prod_pc").value = "0.00";
    if ($("np_prod_pv")) $("np_prod_pv").value = "0.00";
    if ($("np_prod_um")) $("np_prod_um").value = "";

    // Categoría
    if ($("np_cat_nombre")) $("np_cat_nombre").value = "";
    if ($("np_cat_desc")) $("np_cat_desc").value = "";

    // Autocomplete state
    provAcSelected = null;
    hideProvList();

    // Campos editables por defecto
    setProveedorFieldsLocked(false);
  }

  function openNuevoProducto() {
    mountModalToBody();
    clearNuevoProductoForm(); // limpia siempre al abrir

    document.body.style.overflow = "hidden";
    $("modalNuevoProducto").style.display = "flex";

    // Si en la compra principal ya hay proveedor seleccionado, lo colocamos en el modal y buscamos
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
    $("modalNuevoProducto").style.display = "none";
    document.body.style.overflow = "";
    hideProvList();
    clearNuevoProductoForm(); // limpia al cerrar
  }

  async function guardarNuevoProducto() {
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

    if (!prov.nombre.trim()) return toast("err", "Proveedor", "Nombre de proveedor requerido.");
    if (!cat.nombre.trim()) return toast("err", "Categoría", "Nombre de categoría requerido.");
    if (!prod.nombre.trim()) return toast("err", "Producto", "Nombre de producto requerido.");

    const btn = $("btnGuardarNuevoProducto");
    btn.disabled = true;

    try {
      const a = await postForm("/compras/api/proveedor/upsert/", prov);
      if (!a.r.ok || !a.j.ok) return toast("err", "Proveedor", a.j.error || "Error al guardar proveedor.");
      const id_proveedor = a.j.data.id_proveedor;

      const b = await postForm("/compras/api/categoria/upsert/", cat);
      if (!b.r.ok || !b.j.ok) return toast("err", "Categoría", b.j.error || "Error al guardar categoría.");
      const id_categoria = b.j.data.id_categoria;

      const c = await postForm("/compras/api/producto/crear/", { id_proveedor, id_categoria, ...prod });
      if (!c.r.ok || !c.j.ok) return toast("err", "Producto", c.j.error || "Error al crear producto.");

      const newProd = c.j.data;

      // Cerrar modal (también limpia)
      closeNuevoProducto();

      // 1) Recargar proveedores para que el nuevo exista en el <select>
      await loadProveedores();

      // 2) Fallback: si aún no existe como option, lo agregamos manualmente
      const selProv = $("proveedor");
      const idStr = String(id_proveedor);
      if (selProv && !selProv.querySelector(`option[value="${idStr}"]`)) {
        const opt = document.createElement("option");
        opt.value = idStr;
        opt.textContent = prov.nombre.trim();
        selProv.appendChild(opt);
      }

      // 3) Seleccionar proveedor (SIN dispatch change; evita resets)
      $("proveedor").value = idStr;

      // 4) NO borrar items ya agregados; solo preparar cantidad
      $("cantidad").value = "1";

      // 5) Cargar productos y seleccionar el nuevo producto
      await loadProductosByProveedor(idStr);
      $("producto").value = String(newProd.id_producto);

      // Rellenar precios (en moneda actual de visualización)
      $("precio_compra").value = Number(newProd.precio_compra || 0).toFixed(2);
      $("precio_venta").value = Number(newProd.precio_venta || 0).toFixed(2);

      toast("ok", "Producto creado", `Se creó "${newProd.nombre}" y ya está listo para agregar a la compra.`);
    } catch (e) {
      toast("err", "Error", "Error de red/servidor.");
    } finally {
      btn.disabled = false;
    }
  }

  function bindEvents() {
    // Cambiar moneda (convierte montos usando TC manual)
    $("btnToggleCurrency").addEventListener("click", () => {
      const next = state.currency === "NIO" ? "USD" : "NIO";
      tryConvertAll(next);
    });

    // Si el usuario cambia el TC mientras está en USD o NIO, no convertimos automáticamente
    // (para evitar sorpresas). Solo se aplica al dar "Cambiar" o al guardar en USD.
    // Si quieres auto-recalcular, se puede añadir luego.

    $("iva_rate").addEventListener("input", calc);

    $("proveedor").addEventListener("change", (e) => {
      const id_proveedor = e.target.value;

      // Cambiar proveedor SÍ debe limpiar items (es otra compra/proveedor)
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

    $("producto").addEventListener("change", (e) => {
      const p = state.productosMap.get(String(e.target.value));
      if (!p) return;
      $("precio_compra").value = Number(p.precio_compra || 0).toFixed(2);
      $("precio_venta").value = Number(p.precio_venta || 0).toFixed(2);
    });

    $("btnAdd").addEventListener("click", () => {
      const id_producto = $("producto").value;
      const p = state.productosMap.get(String(id_producto));
      const cantidad = parseInt($("cantidad").value, 10);
      const precio_unitario = parseFloat($("precio_compra").value);

      if (!p) return toast("err", "Falta producto", "Selecciona un producto.");
      if (!cantidad || cantidad <= 0) return toast("err", "Cantidad inválida", "La cantidad debe ser mayor que 0.");
      if (isNaN(precio_unitario) || precio_unitario < 0)
        return toast("err", "Precio inválido", "Revisa el precio de compra.");

      const existing = state.items.find((x) => String(x.id_producto) === String(id_producto));
      if (existing) {
        existing.cantidad += cantidad;
        existing.precio_unitario = precio_unitario;
      } else {
        state.items.push({ id_producto: p.id_producto, nombre: p.nombre, cantidad, precio_unitario });
      }

      renderTable();
    });

    $("btnSave").addEventListener("click", async () => {
      const id_proveedor = $("proveedor").value;
      if (!id_proveedor) return toast("err", "Falta proveedor", "Selecciona un proveedor.");
      if (state.items.length === 0) return toast("err", "Sin items", "Agrega al menos un producto.");

      const ivaRate = parseFloat($("iva_rate").value);
      if (isNaN(ivaRate) || ivaRate < 0 || ivaRate > 100)
        return toast("err", "IVA inválido", "IVA debe estar entre 0 y 100.");

      const csrfToken = getCsrf();

      // Guardar SIEMPRE en NIO (C$)
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

      // OJO: ya no enviamos currency, porque DB se guarda en NIO siempre
      // form.append("currency", state.currency);

      form.append("items", JSON.stringify(itemsToSend.map((it) => ({
        id_producto: it.id_producto,
        cantidad: it.cantidad,
        precio_unitario: money(it.precio_unitario), // ya convertido a NIO si hacía falta
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

        state.items = [];
        renderTable();
        $("producto").innerHTML = `<option value="">— Selecciona proveedor primero —</option>`;
        $("precio_compra").value = "0.00";
        $("precio_venta").value = "0.00";
        $("cantidad").value = "1";
        $("proveedor").value = "";

        // Al terminar, volvemos a NIO visualmente (opcional, pero suele ser lo más claro)
        // Si quieres que conserve USD, quita esto:
        state.currency = "NIO";
        setCurrencyUI();
      } catch (e) {
        toast("err", "Error", "Error de red o servidor.");
      } finally {
        btn.disabled = false;
      }
    });

    // Modal open/close
    $("btnNuevoProducto").addEventListener("click", openNuevoProducto);
    $("btnCloseModalNP").addEventListener("click", closeNuevoProducto);
    $("modalBackdrop").addEventListener("click", closeNuevoProducto);
    $("btnGuardarNuevoProducto").addEventListener("click", guardarNuevoProducto);

    // Autocomplete: input proveedor
    if ($("np_prov_nombre")) {
      $("np_prov_nombre").setAttribute("autocomplete", "off");

      $("np_prov_nombre").addEventListener("input", () => {
        const q = $("np_prov_nombre").value.trim();

        // El usuario está escribiendo: dejamos editable para proveedor nuevo
        provAcSelected = null;
        setProveedorFieldsLocked(false);

        if (!q) {
          hideProvList();
          return;
        }

        clearTimeout(provAcTimer);
        provAcTimer = setTimeout(async () => {
          const items = await searchProveedores(q);
          showProvList(items);
        }, 180);
      });
    }

    // Click fuera para cerrar lista
    document.addEventListener("click", (e) => {
      const wrap = $("provAcWrap");
      if (!wrap) return;
      if (!wrap.contains(e.target)) hideProvList();
    });

    // ESC
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && $("modalNuevoProducto")?.style.display === "flex") {
        closeNuevoProducto();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", async () => {
    mountModalToBody();
    bindEvents();
    await loadProveedores();
    setCurrencyUI();
    renderTable();
  });
})();