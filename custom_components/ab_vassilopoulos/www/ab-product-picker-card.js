class ABProductPickerCard extends HTMLElement {
  setConfig(config) {
    const previousEntity = this._config?.todo_entity || null;
    this._config = config;
    if (previousEntity !== (config?.todo_entity || null)) {
      this._searchRequestId = (this._searchRequestId || 0) + 1;
      this._pendingStatuses?.clear();
      this._pendingQuantities?.clear();
      this._selectionRequired = false;
      this._todoActionTasks?.clear();
      this.shadowRoot?.querySelector("#results")?.replaceChildren();
      const status = this.shadowRoot?.querySelector("#status");
      if (status) status.textContent = "";
      const query = this.shadowRoot?.querySelector("#query");
      if (query) query.value = "";
      this._todoEntity = config?.todo_entity || null;
      this._lastTodoState = null;
    }
    this._render();
    this._applyConfig();
  }

  set hass(hass) {
    this._hass = hass;
    const language = this._language();
    const languageChanged = language !== this._lastLanguage;
    const todoEntity = this._config?.todo_entity || null;
    const todoState = todoEntity ? hass.states[todoEntity] : undefined;
    const todoChanged = todoEntity !== this._todoEntity || todoState !== this._lastTodoState;
    this._todoEntity = todoEntity;
    this._lastTodoState = todoState;
    this._updateCardTitle();
    if (languageChanged) {
      this._lastLanguage = language;
      this._applyLanguage();
    }
    if (languageChanged || todoChanged) this._renderTodoList();
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "title", selector: { text: {} } },
        { name: "todo_entity", selector: { entity: { filter: { integration: "ab_vassilopoulos", domain: "todo" } } } },
        { name: "theme", selector: { theme: {} } },
        { name: "show_count", selector: { boolean: {} } },
        { name: "hide_completed", selector: { boolean: {} } },
        { name: "hide_section_headers", selector: { boolean: {} } },
        {
          name: "display_order",
          selector: {
            select: {
              options: this._editorLabels().displayOptions,
              mode: "dropdown",
            },
          },
        },
      ],
      computeLabel: (schema) => ({
        title: this._editorLabels().title,
        todo_entity: this._editorLabels().todo_entity,
        theme: this._editorLabels().theme,
        show_count: this._editorLabels().showCount,
        hide_completed: this._editorLabels().hideCompleted,
        hide_section_headers: this._editorLabels().hideSectionHeaders,
        display_order: this._editorLabels().displayOrder,
      })[schema.name],
    };
  }

  static getStubConfig() {
    return { show_count: true, display_order: "none" };
  }

  static _editorLabels() {
    const isGreek = (document.documentElement.lang || "en").toLowerCase().startsWith("el");
    return isGreek
      ? {
          title: "Τίτλος",
          todo_entity: "Λογαριασμός ΑΒ / λίστα καλαθιού",
          theme: "Θέμα",
          showCount: "Εμφάνιση πλήθους προϊόντων στο καλάθι",
          hideCompleted: "Απόκρυψη ολοκληρωμένων",
          hideSectionHeaders: "Απόκρυψη κεφαλίδων ενεργών και ολοκληρωμένων",
          displayOrder: "Σειρά εμφάνισης",
          displayOptions: [
            { label: "Σειρά προσθήκης", value: "none" },
            { label: "Προσφορές πρώτα", value: "promotions" },
            { label: "Προϊόν: Α έως Ω", value: "alpha_asc" },
            { label: "Προϊόν: Ω έως Α", value: "alpha_desc" },
            { label: "Τιμή: χαμηλότερη πρώτα", value: "price_asc" },
            { label: "Τιμή: υψηλότερη πρώτα", value: "price_desc" },
            { label: "Τιμή ανά τεμάχιο: χαμηλότερη πρώτα", value: "unit_price_asc" },
            { label: "Τιμή ανά τεμάχιο: υψηλότερη πρώτα", value: "unit_price_desc" },
          ],
        }
      : {
          title: "Title",
          todo_entity: "AB account / shopping list",
          theme: "Theme",
          showCount: "Show cart item count",
          hideCompleted: "Hide completed items",
          hideSectionHeaders: "Hide active and completed section headers",
          displayOrder: "Display order",
          displayOptions: [
            { label: "Addition order", value: "none" },
            { label: "Offers first", value: "promotions" },
            { label: "Product: A to Z", value: "alpha_asc" },
            { label: "Product: Z to A", value: "alpha_desc" },
            { label: "Price: lowest first", value: "price_asc" },
            { label: "Price: highest first", value: "price_desc" },
            { label: "Price per item: lowest first", value: "unit_price_asc" },
            { label: "Price per item: highest first", value: "unit_price_desc" },
          ],
        };
  }

  getGridOptions() {
    return { columns: "full" };
  }

  _render() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
    if (this.shadowRoot.childElementCount) {
      return;
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host { color: var(--primary-text-color); font-family: var(--ha-font-family-body, Roboto, sans-serif); }
        .row { display: flex; gap: 8px; }
        ha-input { display:block; box-sizing:border-box; min-width:0; }
        #query { flex:1 1 auto; width:100%; height:56px; }
        #search { --ha-icon-button-size:40px; margin-inline-end:4px; }
        button { min-height:40px; padding:0 16px; border:0; border-radius:var(--ha-button-border-radius, 4px);
          font:inherit; font-weight:500; cursor:pointer; }
        button:disabled { opacity:.5; cursor:default; }
        .filled { color:var(--text-primary-color, #fff); background:var(--primary-color); }
        .plain { color:var(--primary-color); background:transparent; }
        #status { min-height: 1.4em; margin-top: 8px; }
        .card-header { color:var(--ha-card-header-color,var(--primary-text-color)); font-family:var(--ha-card-header-font-family,inherit);
          font-size:var(--ha-card-header-font-size,var(--ha-font-size-2xl,1.5rem)); font-weight:var(--ha-font-weight-normal,400);
          letter-spacing:-.012em; line-height:var(--ha-line-height-condensed,1.2); margin:0; }
        #picker-status { color:var(--secondary-text-color); }
        #picker-status.error { color:var(--error-color); }
        dialog { width: min(560px, calc(100vw - 40px)); max-height: 80vh;
          border: 0; border-radius: 12px; padding: 0; color: var(--primary-text-color);
          background: var(--card-background-color); box-shadow: 0 8px 32px #0005; }
        dialog::backdrop { background: #0007; }
        dialog { overscroll-behavior:contain; }
        .dialog-content { padding: 20px; }
        h2 { margin: 0 0 12px; font-size: 1.25rem; }
        #results { max-height: 55vh; overflow: auto; overscroll-behavior:contain; touch-action:pan-y; }
        .product { display: grid; grid-template-columns: minmax(0, 1fr) auto;
          align-items: center; gap: 10px; padding: 10px 0;
          border-bottom: 1px solid var(--divider-color); }
        .product-name { display: flex; align-items: center; gap: 10px; line-height: 1.3; min-width:0; }
        .product-image { width:56px; height:56px; flex:0 0 56px; object-fit:contain;
          border-radius:4px; background:var(--card-background-color); }
        .product-info, .item-content { display:grid; gap:3px; min-width:0; }
        .product-info { flex:1; }
        .product-title, .item-name { display:block; overflow:hidden; overflow-wrap:anywhere; white-space:normal;
          width:100%; min-width:0; max-width:100%; box-sizing:border-box; }
        .title-text { display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; line-clamp:2;
          overflow:hidden; text-overflow:ellipsis; overflow-wrap:anywhere; white-space:normal;
          width:100%; min-width:0; max-width:100%; box-sizing:border-box; }
        .product-details, .item-details { color:var(--secondary-text-color); font-size:var(--ha-font-size-s); line-height:1.3; }
        .product-details del, .item-details del { margin-inline-end:6px; }
        .product-promotion, .item-promotion { color:var(--success-color, #2e7d32); cursor:pointer; font-size:var(--ha-font-size-s); line-height:1.3;
          display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:1; overflow:hidden; }
        #picker-feedback { display:flex; align-items:center; gap:8px; min-height:1.4em; margin-top:8px; }
        #picker-total, #picker-status { flex:1 1 auto; min-width:0; margin:0; line-height:1.4em;
          white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        #picker-total { font-weight:500; text-align:left; }
        .product-checkbox { box-sizing:border-box; width:20px; min-width:20px; height:20px;
          min-height:20px; flex:0 0 20px; margin:0; accent-color:var(--primary-color); }
        .picker-quantity-control { display:flex; align-items:center; flex:0 0 auto; gap:0; }
        .picker-quantity-control ha-icon-button { --mdc-icon-button-size:36px; --mdc-icon-size:20px; }
        .picker-quantity-value { min-width:2ch; text-align:center; font-variant-numeric:tabular-nums; }
        .actions { display: flex; align-items:center; justify-content: flex-end; gap: 8px; margin-top: 16px; }
        .actions .spacer { flex:1; }
        #more[hidden] { display:none; }
        .list-delete { color:var(--error-color); --mdc-icon-button-size:36px; --mdc-icon-size:20px; flex:0 0 auto; }
        #todo-card { --ha-card-border-width: 0; --ha-card-box-shadow: none;
          --ha-card-background: transparent; }
        .list-row { display:flex; align-items:center; gap:12px; min-height:48px;
          border-bottom:1px solid var(--divider-color); }
        .list-row:last-child { border-bottom:0; }
        .list-row ha-checkbox { flex:0 0 auto; }
        .list-product-image-frame { display:grid; place-items:center; width:40px; height:40px; flex:0 0 40px; }
        .list-product-image { display:block; width:100%; height:100%;
          object-fit:contain; border-radius:4px; pointer-events:none; }
        .image-preview-anchor { cursor:zoom-in; border:0; padding:0; color:inherit; background:transparent; }
        .product-image { cursor:zoom-in; }
        .name-tooltip.image-tooltip { width:auto !important; max-width:min(75vw, 420px); max-height:60vh; padding:6px; overflow:hidden; }
        .image-tooltip img { display:block; width:auto; height:auto; max-width:min(75vw, 420px);
          max-height:60vh; object-fit:contain; border-radius:4px; }
        .item-content { flex:1; }
        .item-name { min-width:0; overflow-wrap:anywhere; }
        .product-title, .item-name { appearance:none; min-height:0; padding:0; border:0; border-radius:0;
          color:inherit; background:transparent; font:inherit; font-weight:inherit; line-height:1.4em; text-align:start; cursor:pointer; }
        .product-select { display:flex; align-items:center; gap:10px; }
        .quantity-control { display:flex; align-items:center; flex:0 0 auto; gap:0; }
        .quantity-control ha-icon-button { --mdc-icon-button-size:36px; --mdc-icon-size:20px; }
        .quantity-value { min-width:2ch; text-align:center; font-variant-numeric:tabular-nums; }
        .completed .item-name { text-decoration:line-through; color:var(--secondary-text-color); }
        .item-name.unavailable { color:var(--error-color); }
        .section-title { color:var(--primary-text-color); font-size:var(--ha-font-size-m);
          font-weight:500; line-height:var(--ha-line-height-normal); margin:16px 0 8px; }
        #cart-count { flex: 0 0 auto; border-radius: 999px; padding: 3px 10px;
          background: var(--primary-color); color: var(--text-primary-color, white);
          font-size: var(--ha-font-size-m); line-height: var(--ha-line-height-normal); }
        #cart-count[hidden] { display: none; }
        #name-tooltip, .name-tooltip { position:fixed; z-index:10000; max-width:min(320px, calc(100vw - 24px));
          padding:10px 12px; border-radius:8px; color:var(--primary-text-color);
          background:var(--card-background-color); box-shadow:0 4px 18px #0005;
          font:var(--ha-font-size-m, 14px)/1.4 var(--ha-font-family-body, Roboto, sans-serif);
          white-space:normal; overflow-wrap:anywhere; pointer-events:auto; box-sizing:border-box; max-height:45vh; overflow:auto;
          width:max-content; }
        .name-tooltip[hidden] { display:none; }
      </style>
      <div id="list-name-tooltip" class="name-tooltip" role="tooltip" hidden></div>
      <ha-card>
        <h1 class="card-header" style="display:flex;align-items:center;justify-content:space-between;gap:12px"><span id="title"></span><span id="cart-count" hidden></span></h1>
        <div class="card-content">
          <div class="row">
            <ha-input id="query" type="search" autocomplete="off">
              <ha-icon-button id="search" slot="end"></ha-icon-button>
            </ha-input>
          </div>
          <div id="status" role="status"></div>
          <div id="todo-card"></div>
        </div>
      </ha-card>
      <dialog id="picker">
        <div class="dialog-content">
          <div id="picker-name-tooltip" class="name-tooltip" role="tooltip" hidden></div>
          <h2 id="dialog-title"></h2>
          <div id="results"></div>
          <div id="picker-feedback">
            <div id="picker-total" hidden></div>
            <div id="picker-status" role="status" hidden></div>
          </div>
          <div class="actions">
            <ha-button id="more" appearance="plain" hidden></ha-button>
            <span class="spacer"></span>
            <ha-button id="cancel" appearance="plain"></ha-button>
            <ha-button id="add" appearance="filled"></ha-button>
          </div>
        </div>
      </dialog>
    `;

    window.addEventListener("scroll", () => this._hideNameTooltip(), true);
    const pickerDialog = this.shadowRoot.querySelector("#picker");
    const pickerResults = this.shadowRoot.querySelector("#results");
    for (const tooltip of this.shadowRoot.querySelectorAll(".name-tooltip")) {
      tooltip.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        this._hideNameTooltip();
      });
    }
    pickerDialog.addEventListener("scroll", () => this._hideNameTooltip(), true);
    pickerResults.addEventListener("scroll", () => this._hideNameTooltip(), { passive: true });
    const preventBackgroundScroll = (event) => {
      if (pickerDialog.open && !event.composedPath().includes(pickerDialog)) {
        event.preventDefault();
      }
    };
    window.addEventListener("wheel", preventBackgroundScroll, { capture: true, passive: false });
    window.addEventListener("touchmove", preventBackgroundScroll, { capture: true, passive: false });
    window.addEventListener("pointerdown", (event) => {
      if (!this._activeNameTooltip || this._activeNameTooltip.hidden) return;
      const path = event.composedPath();
      if (!path.includes(this._activeNameTooltip) &&
          !path.includes(this._activeNameTarget)) this._hideNameTooltip();
    }, true);
    const searchButton = this.shadowRoot.querySelector("#search");
    searchButton.path = "M9.5 3a6.5 6.5 0 1 0 3.98 11.64l.27.27v.76l5 5L20.5 19l-5-5h-.76l-.27-.27A6.5 6.5 0 0 0 9.5 3Zm0 2a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9Z";
    searchButton.addEventListener("click", () => this._search());
    this.shadowRoot.querySelector("#query").addEventListener("input", (event) => {
      this._searchRequestId = (this._searchRequestId || 0) + 1;
      this.shadowRoot.querySelector("#status").textContent = "";
      searchButton.disabled = false;
      this.shadowRoot.querySelector("#results").replaceChildren();
      this.shadowRoot.querySelector("#more").hidden = true;
      this._searchQuery = "";
      this._nextSearchPage = 0;
      const dialog = this.shadowRoot.querySelector("#picker");
      if (dialog.open) dialog.close();
      if (!event.target.value.trim()) {
        this._selectionRequired = false;
      }
    });
    this.shadowRoot.querySelector("#query").addEventListener("keydown", (event) => {
      if (event.key === "Enter") this._search();
    });
    this.shadowRoot.querySelector("#cancel").addEventListener("click", () => {
      this.shadowRoot.querySelector("#picker").close();
    });
    this.shadowRoot.querySelector("#more").addEventListener("click", () => this._loadMore());
    const results = this.shadowRoot.querySelector("#results");
    const updateProductDetails = (event) => {
      const row = event.target.closest?.(".product");
      if (row) this._updateProductRow(row);
      this._updatePickerTotal();
    };
    results.addEventListener("change", updateProductDetails);
    this.shadowRoot.querySelector("#add").addEventListener("click", () => this._addSelected());
    this.shadowRoot.querySelector("#todo-card").addEventListener("change", (event) => this._handleListChange(event));
    for (const dialog of this.shadowRoot.querySelectorAll("dialog")) {
      dialog.addEventListener("click", (event) => {
        if (event.target === dialog) dialog.close();
      });
    }
  }

  _applyConfig() {
    if (!this.shadowRoot?.childElementCount) return;
    const card = this.shadowRoot.querySelector("ha-card");
    if (this._config.theme) {
      this.setAttribute("theme", this._config.theme);
      card.setAttribute("theme", this._config.theme);
    } else {
      this.removeAttribute("theme");
      card.removeAttribute("theme");
    }
    this._updateCardTitle();
    this._updateCountBadge();
    const entity = this._resolveTodoEntity();
    this._todoEntity = entity;
    this._renderTodoList();
  }

  _resolveTodoEntity() {
    return this._config?.todo_entity || null;
  }

  _accountName() {
    const friendlyName = String(
      this._hass?.states[this._resolveTodoEntity()]?.attributes?.friendly_name || "",
    ).trim();
    const account = friendlyName.match(/\(([^()]*)\)\s*$/);
    return account?.[1]?.trim() || friendlyName;
  }

  _updateCardTitle() {
    const title = this.shadowRoot?.querySelector("#title");
    if (!title) return;
    const customTitle = String(this._config?.title || "").trim();
    const account = this._accountName();
    const language = this._language();
    title.textContent = customTitle || (account
      ? `${language === "el" ? "Καλάθι" : "Cart"} · ${account}`
      : language === "el" ? "Καλάθι ΑΒ" : "AB cart");
  }

  _nativeTodoConfig(entity) { return { type: "todo-list", entity }; }

  _updateCountBadge() {
    if (!this.shadowRoot?.childElementCount) return;
    const badge = this.shadowRoot.querySelector("#cart-count");
    const state = this._hass?.states[this._config?.todo_entity];
    let count = Number(state?.attributes?.cart_total_quantity);
    const stateRows = state?.attributes?.ab_items || [];
    for (const [uid, wanted] of this._pendingStatuses || []) {
      const item = stateRows.find((row) => row.uid === uid);
      if (!item) continue;
      const isActive = item.status !== "completed";
      if (isActive && wanted === "completed") count -= Number(item.quantity || 1);
      if (!isActive && wanted !== "completed") count += Number(item.quantity || 1);
    }
    for (const [uid, quantity] of this._pendingQuantities || []) {
      const item = stateRows.find((row) => row.uid === uid);
      if (!item) continue;
      const isActive = item.status !== "completed";
      if (isActive) count += Number(quantity) - Number(item.quantity || 1);
    }
    badge.hidden = this._config.show_count === false || !Number.isFinite(count);
    badge.textContent = Number.isFinite(count) ? `${count}` : "";
    if (Number.isFinite(count)) badge.setAttribute("aria-label", this._strings().cartCount(count));
    this.shadowRoot.querySelector(".card-header").hidden =
      !this._resolvedCardTitle() && badge.hidden;
  }

  _resolvedCardTitle() {
    return String(this._config?.title || this._accountName() || "cart").trim();
  }

  async _loadTodoList() {
    this._todoEntity = this._resolveTodoEntity();
    this._renderTodoList();
  }

  _quantityTotalPrice(item, quantity) {
    const unitPrice = Number(item.unit_price);
    if (!Number.isFinite(unitPrice)) return item.total_price;

    const buyQuantity = Number(item.bundle_buy_quantity) || 0;
    const freeQuantity = Number(item.bundle_free_quantity) || 0;
    const offerSize = buyQuantity + freeQuantity;
    if (offerSize > 0) {
      const paidQuantity = quantity - Math.floor(quantity / offerSize) * freeQuantity;
      return Math.round(unitPrice * paidQuantity * 100) / 100;
    }

    const percentage = Number(item.discount_percent);
    if (Number.isFinite(percentage)) {
      const basePrice = Number(item.regular_price ?? unitPrice);
      const threshold = Math.max(1, Number(item.discount_min_quantity) || 1);
      const discountedQuantity = Math.floor(quantity / threshold) * threshold;
      const discountedUnitCents = Math.round(Math.round(basePrice * 100) * (100 - percentage) / 100);
      const regularUnitCents = Math.round(basePrice * 100);
      const regularQuantity = quantity - discountedQuantity;
      return (discountedUnitCents * discountedQuantity + regularUnitCents * regularQuantity) / 100;
    }

    return Math.round(unitPrice * quantity * 100) / 100;
  }

  _renderTodoList() {
    const container = this.shadowRoot?.querySelector("#todo-card");
    if (!container || !this._hass) return;
    const query = this.shadowRoot.querySelector("#query");
    const search = this.shadowRoot.querySelector("#search");
    const status = this.shadowRoot.querySelector("#status");
    if (!this._todoEntity) {
      query.disabled = true;
      search.disabled = true;
      container.replaceChildren();
      status.textContent = this._strings().selectAccount;
      this._updateCountBadge();
      return;
    }
    query.disabled = false;
    search.disabled = false;
    if (status.textContent === this._strings().selectAccount) status.textContent = "";
    this._updateCountBadge();
    const rows = (this._hass.states[this._config.todo_entity]?.attributes?.ab_items || []).map((row) => ({ ...row }));
    this._pendingQuantities ||= new Map();
    this._pendingStatuses ||= new Map();
    this._settledStatuses ||= new Map();
    for (const [uid, wanted] of this._pendingStatuses) {
      const actual = rows.find((row) => row.uid === uid);
      if (actual?.status === wanted && this._settledStatuses.get(uid) === wanted) {
        this._pendingStatuses.delete(uid);
        this._settledStatuses.delete(uid);
      } else if (actual) {
        actual.status = wanted;
      }
    }
    for (const [uid, wanted] of this._pendingQuantities) {
      const actual = rows.find((row) => row.uid === uid);
      if (Number(actual?.quantity) === Number(wanted)) this._pendingQuantities.delete(uid);
      else if (actual) {
        actual.quantity = wanted;
        actual.total_price = this._quantityTotalPrice(actual, Number(wanted));
      }
    }
    const collator = new Intl.Collator(this._language());
    const order = this._config.display_order || "none";
    if (order === "promotions") {
      rows.sort((a, b) => Number((b.promotions || []).length > 0) - Number((a.promotions || []).length > 0));
    }
    if (order === "alpha_asc") rows.sort((a, b) => collator.compare(a.name, b.name));
    if (order === "alpha_desc") rows.sort((a, b) => collator.compare(b.name, a.name));
    if (["price_asc", "price_desc", "unit_price_asc", "unit_price_desc"].includes(order)) {
      const byUnitPrice = order.startsWith("unit_price_");
      const direction = order.endsWith("asc") ? 1 : -1;
      const priceKey = byUnitPrice ? "unit_price" : "total_price";
      rows.sort((a, b) => {
        const priceA = a[priceKey] == null ? NaN : Number(a[priceKey]);
        const priceB = b[priceKey] == null ? NaN : Number(b[priceKey]);
        const hasPriceA = Number.isFinite(priceA);
        const hasPriceB = Number.isFinite(priceB);
        if (hasPriceA !== hasPriceB) return hasPriceA ? -1 : 1;
        if (!hasPriceA) return 0;
        return (priceA - priceB) * direction;
      });
    }
    const active = rows.filter((row) => row.status !== "completed");
    const completed = rows.filter((row) => row.status === "completed");
    container.replaceChildren();
    const renderSection = (label, items, status) => {
      if (!items.length) return;
      if (!this._config.hide_section_headers) {
        const header = document.createElement("div");
        header.className = "section-title";
        header.textContent = label;
        container.append(header);
      }
      for (const item of items) {
        const row = document.createElement("div");
        row.className = `list-row${status === "completed" ? " completed" : ""}`;
        row.dataset.uid = item.uid;
        row.dataset.name = item.name;
        const quantity = Math.max(1, Number(item.quantity) || 1);
        row.dataset.quantity = String(quantity);
        row.dataset.summary = status === "completed" ? item.name : `${item.name} × ${item.quantity || 1}`;
        const checkbox = document.createElement("ha-checkbox");
        checkbox.checked = status === "completed";
        checkbox.setAttribute("aria-label", this._strings().toggleItem(item.name));
        const imageFrame = document.createElement("span");
        imageFrame.className = "list-product-image-frame";
        if (item.image_url) {
          const image = document.createElement("img");
          image.className = "list-product-image";
          image.src = item.image_url;
          image.alt = "";
          image.loading = "lazy";
          image.decoding = "async";
          image.referrerPolicy = "no-referrer";
          image.addEventListener("error", () => image.remove(), { once: true });
          imageFrame.classList.add("image-preview-anchor");
          this._bindImagePreview(imageFrame, image, item.name);
          imageFrame.append(image);
        }
        const name = document.createElement("button");
        name.type = "button";
        name.className = "item-name";
        if (status !== "completed" && item.available === false) name.classList.add("unavailable");
        const titleText = document.createElement("span");
        titleText.className = "title-text";
        titleText.textContent = item.name;
        name.append(titleText);
        name.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          this._showNameTooltip(name, name.textContent);
        });
        const content = document.createElement("div");
        content.className = "item-content";
        content.append(name);
        if (status !== "completed") {
          const unitPrice = Number(item.unit_price);
          if (item.unit_price != null && Number.isFinite(unitPrice)) {
            const details = document.createElement("div");
            details.className = "item-details";
            this._renderListPrice(details, item, quantity);
            content.append(details);
          }
          const promotions = (item.promotions || [])
            .map((promotion) => promotion.title || promotion.description)
            .filter(Boolean);
          if (promotions.length) {
            const offer = document.createElement("div");
            offer.className = "item-promotion";
            offer.textContent = promotions.join(" · ");
            offer.setAttribute("role", "button");
            offer.setAttribute("tabindex", "0");
            offer.addEventListener("click", (event) => {
              event.preventDefault();
              event.stopPropagation();
              this._showNameTooltip(offer, offer.textContent);
            });
            offer.addEventListener("keydown", (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                this._showNameTooltip(offer, offer.textContent);
              }
            });
            content.append(offer);
          }
        }
        let quantityControl;
        if (status !== "completed") {
          quantityControl = document.createElement("div");
          quantityControl.className = "quantity-control";
          const decrement = document.createElement("ha-icon-button");
          decrement.path = "M19 13H5v-2h14v2Z";
          decrement.setAttribute("aria-label", this._strings().decreaseQuantity(item.name));
          decrement.disabled = quantity <= 1;
          decrement.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            this._changeQuantity(row, -1);
          });
          const value = document.createElement("span");
          value.className = "quantity-value";
          value.textContent = String(quantity);
          const increment = document.createElement("ha-icon-button");
          increment.path = "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2Z";
          increment.setAttribute("aria-label", this._strings().increaseQuantity(item.name));
          increment.disabled = quantity >= 99;
          increment.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            this._changeQuantity(row, 1);
          });
          quantityControl.append(decrement, value, increment);
        }
        row.append(checkbox);
        row.append(imageFrame);
        row.append(content);
        if (quantityControl) row.append(quantityControl);
        if (status === "completed") {
          const removeButton = document.createElement("ha-icon-button");
          removeButton.className = "list-delete";
          removeButton.path = "M9 3v1H4v2h1v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V6h1V4h-5V3H9Zm0 4h2v10H9V7Zm4 0h2v10h-2V7Z";
          removeButton.setAttribute("aria-label", this._strings().deleteItem(item.name));
          removeButton.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            this._deleteListItem(item.uid);
          });
          row.append(removeButton);
        }
        container.append(row);
      }
    };
    renderSection(this._strings().active, active, "needs_action");
    if (!this._config.hide_completed) renderSection(this._strings().completed, completed, "completed");
  }

  _showNameTooltip(button, text) {
    const tooltip = this.shadowRoot.querySelector(button.classList.contains("product-title") ? "#picker-name-tooltip" : "#list-name-tooltip");
    if (this._activeNameTarget === button && !tooltip.hidden) {
      this._hideNameTooltip();
      return;
    }
    this._activeNameTarget = button;
    this._activeNameTooltip = tooltip;
    tooltip.classList.remove("image-tooltip");
    tooltip.replaceChildren(document.createTextNode(text));
    tooltip.style.width = `${Math.max(1, button.getBoundingClientRect().width)}px`;
    tooltip.hidden = false;
    const rect = button.getBoundingClientRect();
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - tooltip.offsetWidth - 8));
    const top = rect.top + tooltip.offsetHeight <= window.innerHeight - 8
      ? rect.top
      : Math.max(8, rect.bottom - tooltip.offsetHeight);
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
    clearTimeout(this._nameTooltipTimer);
    this._nameTooltipTimer = setTimeout(() => this._hideNameTooltip(), 4000);
  }

  _bindImagePreview(anchor, image, name) {
    anchor.setAttribute("role", "button");
    anchor.setAttribute("tabindex", "0");
    anchor.setAttribute("aria-label", name);
    const open = (event) => {
      event.preventDefault();
      event.stopPropagation();
      this._showImageTooltip(anchor, image);
    };
    anchor.addEventListener("click", open);
    anchor.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") open(event);
    });
  }

  _showImageTooltip(anchor, image) {
    const tooltip = this.shadowRoot.querySelector(anchor.closest("#picker") ? "#picker-name-tooltip" : "#list-name-tooltip");
    const preview = document.createElement("img");
    preview.src = image.currentSrc || image.src;
    preview.alt = image.alt || "";
    tooltip.replaceChildren(preview);
    tooltip.classList.add("image-tooltip");
    this._activeNameTarget = anchor;
    this._activeNameTooltip = tooltip;
    tooltip.style.width = "auto";
    tooltip.hidden = false;
    const position = () => {
      const rect = anchor.getBoundingClientRect();
      const left = Math.max(8, Math.min(rect.left + (rect.width - tooltip.offsetWidth) / 2, window.innerWidth - tooltip.offsetWidth - 8));
      const top = Math.max(8, Math.min(rect.top + (rect.height - tooltip.offsetHeight) / 2, window.innerHeight - tooltip.offsetHeight - 8));
      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${top}px`;
    };
    requestAnimationFrame(position);
    clearTimeout(this._nameTooltipTimer);
    this._nameTooltipTimer = setTimeout(() => this._hideNameTooltip(), 4000);
  }

  _hideNameTooltip() {
    const tooltip = this._activeNameTooltip;
    if (tooltip) { tooltip.hidden = true; tooltip.classList.remove("image-tooltip"); tooltip.replaceChildren(); }
    this._activeNameTooltip = null;
    this._activeNameTarget = null;
    clearTimeout(this._nameTooltipTimer);
  }

  _renderListPrice(details, item, quantity) {
    const unitPrice = Number(item.unit_price);
    if (!Number.isFinite(unitPrice)) return;
    const unitLabel = this._formatMoney(unitPrice);
    const buyQuantity = Number(item.bundle_buy_quantity) || 0;
    const freeQuantity = Number(item.bundle_free_quantity) || 0;
    const offerSize = buyQuantity + freeQuantity;
    const paidQuantity = offerSize > 0
      ? quantity - Math.floor(quantity / offerSize) * freeQuantity
      : quantity;
    const totalPrice = this._quantityTotalPrice(item, quantity);
    const discountMinQuantity = Number(item.discount_min_quantity) || 1;
    details.replaceChildren();
    if (
      !offerSize
      && item.regular_price != null
      && Number(item.regular_price) * quantity > totalPrice
    ) {
      const oldPrice = document.createElement("del");
      oldPrice.textContent = this._formatMoney(item.regular_price);
      details.append(oldPrice, document.createTextNode(" "));
    }
    details.append(document.createTextNode(
      discountMinQuantity > 1
        ? this._strings().quantityTotal(this._formatMoney(totalPrice))
        : quantity > 1
          ? `${unitLabel} × ${paidQuantity} = ${this._formatMoney(totalPrice)}`
          : unitLabel
    ));
  }

  _changeQuantity(row, delta) {
    const uid = row.dataset.uid;
    const stateRows = this._hass?.states[this._config?.todo_entity]?.attributes?.ab_items || [];
    const item = stateRows.find((entry) => String(entry.uid) === uid);
    if (!item) return;
    this._pendingQuantities ||= new Map();
    this._desiredQuantities ||= new Map();
    this._quantityTasks ||= new Map();
    this._quantityTimers ||= new Map();
    const currentQuantity = Number(this._pendingQuantities.get(uid) ?? row.dataset.quantity) || 1;
    const quantity = Math.max(1, Math.min(99, currentQuantity + delta));
    if (quantity === currentQuantity) return;

    const serverQuantity = Math.max(1, Number(item.quantity) || 1);
    const taskInProgress = this._quantityTasks.has(uid);
    if (quantity === serverQuantity && !taskInProgress) {
      this._pendingQuantities.delete(uid);
      this._desiredQuantities.delete(uid);
      clearTimeout(this._quantityTimers.get(uid));
      this._quantityTimers.delete(uid);
    } else {
      this._pendingQuantities.set(uid, quantity);
      this._desiredQuantities.set(uid, quantity);
      clearTimeout(this._quantityTimers.get(uid));
      this._quantityTimers.set(uid, setTimeout(() => {
        this._quantityTimers.delete(uid);
        this._startQuantityUpdates(uid);
      }, 250));
    }

    row.dataset.quantity = String(quantity);
    row.dataset.summary = `${row.dataset.name} × ${quantity}`;
    row.querySelector(".quantity-value").textContent = String(quantity);
    const buttons = row.querySelectorAll(".quantity-control ha-icon-button");
    buttons[0].disabled = quantity <= 1;
    buttons[1].disabled = quantity >= 99;
    const details = row.querySelector(".item-details");
    if (details) this._renderListPrice(details, item, quantity);
    this._updateCountBadge();
  }

  _startQuantityUpdates(uid) {
    if (this._quantityTasks.has(uid)) return;
    const task = this._flushQuantityUpdates(uid);
    this._quantityTasks.set(uid, task);
  }

  async _flushQuantityUpdates(uid) {
    try {
      while (this._desiredQuantities.has(uid)) {
        const quantity = this._desiredQuantities.get(uid);
        this._desiredQuantities.delete(uid);
        const item = (this._hass?.states[this._config?.todo_entity]?.attributes?.ab_items || [])
          .find((entry) => String(entry.uid) === uid);
        const row = [...this.shadowRoot.querySelectorAll(".list-row")]
          .find((entry) => entry.dataset.uid === uid);
        const name = item?.name || row?.dataset.name;
        if (!name) continue;
        await this._callTodoQueued(uid, "update_item", {
          item: uid,
          rename: `${name} × ${quantity}`,
        });
      }
      this._renderTodoList();
    } catch (error) {
      this._desiredQuantities.delete(uid);
      this._pendingQuantities.delete(uid);
      this._renderTodoList();
      this.shadowRoot.querySelector("#status").textContent = error?.message || this._strings().editFailed;
    } finally {
      this._quantityTasks.delete(uid);
      if (this._desiredQuantities.has(uid)) this._startQuantityUpdates(uid);
    }
  }

  _handleListChange(event) {
    if (!event.target.matches(".list-row ha-checkbox")) return;
    const row = event.target.closest(".list-row");
    this._changeStatus(row, event.target.checked ? "completed" : "needs_action");
  }

  _changeStatus(row, status) {
    this._pendingStatuses ||= new Map();
    this._desiredStatuses ||= new Map();
    this._statusTasks ||= new Map();
    this._settledStatuses ||= new Map();
    this._pendingStatuses.set(row.dataset.uid, status);
    this._settledStatuses.delete(row.dataset.uid);
    this._desiredStatuses.set(row.dataset.uid, status);
    // Keep the clicked checkbox node alive while it is handling its change
    // event. Replacing the list here can make a rapid second click act on a
    // newly rendered, stale checkbox value.
    row.classList.toggle("completed", status === "completed");
    this._updateCountBadge();
    this._statusTimers ||= new Map();
    clearTimeout(this._statusTimers.get(row.dataset.uid));
    this._statusTimers.set(row.dataset.uid, setTimeout(() => {
      this._statusTimers.delete(row.dataset.uid);
      this._startStatusUpdates(row.dataset.uid);
    }, 180));
  }

  _startStatusUpdates(uid) {
    if (this._statusTasks.has(uid)) return;
    const task = this._flushStatusUpdates(uid);
    this._statusTasks.set(uid, task);
  }

  async _flushStatusUpdates(uid) {
    try {
      while (this._desiredStatuses.has(uid)) {
        const status = this._desiredStatuses.get(uid);
        this._desiredStatuses.delete(uid);
        await this._callTodoQueued(uid, "update_item", { item: uid, status });
      }
      const settled = this._pendingStatuses.get(uid);
      if (settled) this._settledStatuses.set(uid, settled);
      this._renderTodoList();
    } catch (error) {
      if (!this._desiredStatuses.has(uid)) {
        this._pendingStatuses.delete(uid);
        this._settledStatuses.delete(uid);
        this._renderTodoList();
      }
    } finally {
      this._statusTasks.delete(uid);
      if (this._desiredStatuses.has(uid)) {
        this._startStatusUpdates(uid);
      }
    }
  }

  async _deleteListItem(uid) {
    this._deletingItems ||= new Set();
    if (this._deletingItems.has(uid)) return;
    this._deletingItems.add(uid);
    const row = [...this.shadowRoot.querySelectorAll(".list-row")]
      .find((entry) => entry.dataset.uid === String(uid));
    const button = row?.querySelector(".list-delete");
    if (button) button.disabled = true;
    try {
      await this._callTodo("remove_item", { item: uid });
    } catch (error) {
      if (button) button.disabled = false;
      this.shadowRoot.querySelector("#status").textContent = error?.message || this._strings().deleteFailed;
    } finally {
      this._deletingItems.delete(uid);
    }
  }

  _callTodo(service, data) {
    const entityId = this._config?.todo_entity;
    if (!entityId) return;
    return this._hass.callService("todo", service, { entity_id: entityId, ...data });
  }

  _callTodoQueued(uid, service, data) {
    const entityId = this._config?.todo_entity;
    if (!entityId) return Promise.resolve();
    this._todoActionTasks ||= new Map();
    const previous = this._todoActionTasks.get(uid) || Promise.resolve();
    const next = previous.catch(() => {}).then(() =>
      this._hass.callService("todo", service, { entity_id: entityId, ...data })
    );
    this._todoActionTasks.set(uid, next);
    next.then(
      () => { if (this._todoActionTasks.get(uid) === next) this._todoActionTasks.delete(uid); },
      () => { if (this._todoActionTasks.get(uid) === next) this._todoActionTasks.delete(uid); },
    );
    return next;
  }

  _language() {
    const language = this._hass?.locale?.language || "en";
    return language.toLowerCase().startsWith("el") ? "el" : "en";
  }

  _strings() {
    const translations = {
      en: {
        searchPlaceholder: "Search AB products",
        selectAccount: "Select an AB account in card settings.",
        search: "Search",
        dialogTitle: "Choose products",
        cancel: "Cancel",
        addSelected: "Add selected",
        searching: "Searching…",
        found: (count) => `${count} suggestions found.`,
        toggleProduct: (name) => `Select ${name}`,
        expandName: (name) => `Show full name: ${name}`,
        collapseName: (name) => `Collapse name: ${name}`,
        more: "Show more",
        noneFound: "No products found.",
        searchFailed: "Search failed.",
        decreaseQuantity: (name) => `Decrease quantity for ${name}`,
        increaseQuantity: (name) => `Increase quantity for ${name}`,
        added: (count) => `Added ${count} units to the cart.`,
        selectProduct: "Select at least one product.",
        addFailed: "Could not add the selected products.",
        editFailed: "Could not save the quantity.",
        todoLoadFailed: "Could not load the AB shopping list.",
        cartCount: (count) => `${count} items in cart`,
        priceUnavailable: "Price unavailable",
        selectedTotal: (total) => `Total: ${total}`,
        quantityTotal: (total) => `Total: ${total}`,
        active: "In cart", completed: "Completed", toggleItem: (name) => `Mark ${name} complete`,
        deleteItem: (name) => `Remove ${name}`,
        deleteFailed: "Could not remove the item.",
      },
      el: {
        searchPlaceholder: "Αναζήτηση προϊόντων ΑΒ",
        selectAccount: "Επίλεξε λογαριασμό ΑΒ στις ρυθμίσεις της κάρτας.",
        search: "Αναζήτηση",
        dialogTitle: "Επιλογή προϊόντων",
        cancel: "Άκυρο",
        addSelected: "Προσθήκη επιλεγμένων",
        searching: "Αναζήτηση…",
        found: (count) => `Βρέθηκαν ${count} προτάσεις.`,
        toggleProduct: (name) => `Επιλογή ${name}`,
        expandName: (name) => `Εμφάνιση πλήρους ονόματος: ${name}`,
        collapseName: (name) => `Σύμπτυξη ονόματος: ${name}`,
        more: "Εμφάνιση περισσότερων",
        noneFound: "Δεν βρέθηκαν προϊόντα.",
        searchFailed: "Η αναζήτηση απέτυχε.",
        decreaseQuantity: (name) => `Μείωση ποσότητας για ${name}`,
        increaseQuantity: (name) => `Αύξηση ποσότητας για ${name}`,
        added: (count) => `Προστέθηκαν ${count} τεμάχια στο καλάθι.`,
        selectProduct: "Επίλεξε τουλάχιστον ένα προϊόν.",
        addFailed: "Δεν ήταν δυνατή η προσθήκη προϊόντων.",
        editFailed: "Δεν ήταν δυνατή η αποθήκευση της ποσότητας.",
        todoLoadFailed: "Δεν ήταν δυνατή η φόρτωση της λίστας αγορών.",
        cartCount: (count) => `${count} προϊόντα στο καλάθι`,
        priceUnavailable: "Δεν υπάρχει διαθέσιμη τιμή",
        selectedTotal: (total) => `Σύνολο: ${total}`,
        quantityTotal: (total) => `Σύνολο: ${total}`,
        active: "Στο καλάθι", completed: "Ολοκληρωμένα", toggleItem: (name) => `Ολοκλήρωση ${name}`,
        deleteItem: (name) => `Αφαίρεση ${name}`,
        deleteFailed: "Δεν ήταν δυνατή η αφαίρεση του προϊόντος.",
      },
    };
    return translations[this._language()];
  }

  _applyLanguage() {
    if (!this.shadowRoot?.childElementCount) return;
    const text = this._strings();
    const query = this.shadowRoot.querySelector("#query");
    query.placeholder = text.searchPlaceholder;
    query.setAttribute("aria-label", text.searchPlaceholder);
    const searchButton = this.shadowRoot.querySelector("#search");
    searchButton.label = text.search;
    this.shadowRoot.querySelector("#dialog-title").textContent = text.dialogTitle;
    this.shadowRoot.querySelector("#cancel").textContent = text.cancel;
    this.shadowRoot.querySelector("#add").textContent = text.addSelected;
    this.shadowRoot.querySelector("#more").textContent = text.more;
  }

  async _search() {
    const query = this.shadowRoot.querySelector("#query").value.trim();
    const status = this.shadowRoot.querySelector("#status");
    if (!this._todoEntity) {
      status.textContent = this._strings().selectAccount;
      return;
    }
    if (!query || !this._hass) return;
    const requestId = this._searchRequestId = (this._searchRequestId || 0) + 1;
    const text = this._strings();
    status.textContent = text.searching;
    this._searchQuery = query;
    this._nextSearchPage = 0;
    this.shadowRoot.querySelector("#more").hidden = true;
    this.shadowRoot.querySelector("#search").disabled = true;
    try {
      const result = await this._requestSearchPage(query, 0);
      if (requestId !== this._searchRequestId || query !== this.shadowRoot.querySelector("#query").value.trim()) return;
      this._searchQuery = result.query || query;
      this._nextSearchPage = 1;
      this._showProducts(result.products || []);
      this.shadowRoot.querySelector("#more").hidden = !result.has_more;
      status.textContent = result.products?.length
        ? text.found(result.total_results || result.products.length)
        : text.noneFound;
    } catch (error) {
      if (requestId === this._searchRequestId) status.textContent = text.searchFailed;
    } finally {
      if (requestId === this._searchRequestId) this.shadowRoot.querySelector("#search").disabled = false;
    }
  }

  async _requestSearchPage(query, page) {
    const result = await this._hass.callWS({
      type: "call_service",
      domain: "ab_vassilopoulos",
      service: "search_products",
      service_data: { query, page, entity_id: this._config?.todo_entity },
      return_response: true,
    });
    return result?.response || {};
  }

  async _loadMore() {
    const button = this.shadowRoot.querySelector("#more");
    if (button.disabled || !this._searchQuery) return;
    const query = this._searchQuery;
    const requestId = this._searchRequestId;
    button.disabled = true;
    try {
      const result = await this._requestSearchPage(query, this._nextSearchPage);
      if (requestId !== this._searchRequestId || query !== this._searchQuery) return;
      this._showProducts(result.products || [], true);
      this._nextSearchPage += 1;
      button.hidden = !result.has_more;
      const count = this.shadowRoot.querySelectorAll("#results .product").length;
      this.shadowRoot.querySelector("#status").textContent = this._strings().found(
        result.total_results || count
      );
    } catch (error) {
      if (requestId === this._searchRequestId) {
        this.shadowRoot.querySelector("#status").textContent = this._strings().searchFailed;
      }
    } finally {
      button.disabled = false;
    }
  }

  _showProducts(products, append = false) {
    const results = this.shadowRoot.querySelector("#results");
    if (!append) results.replaceChildren();
    const existingCodes = new Set(
      [...results.querySelectorAll(".product-checkbox")].map((checkbox) => checkbox.dataset.code)
    );
    const pickerStatus = this.shadowRoot.querySelector("#picker-status");
    pickerStatus.textContent = "";
    pickerStatus.classList.remove("error");
    pickerStatus.hidden = true;
    this._selectionRequired = false;
    for (const product of products) {
      if (existingCodes.has(String(product.code))) continue;
      existingCodes.add(String(product.code));
      const row = document.createElement("div");
      row.className = "product";
      const productName = document.createElement("div");
      productName.className = "product-name";
      const selectionLabel = document.createElement("label");
      selectionLabel.className = "product-select";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.className = "product-checkbox";
      checkbox.dataset.code = product.code;
      checkbox.dataset.name = product.name;
      checkbox.setAttribute("aria-label", this._strings().toggleProduct(product.name));
      const name = document.createElement("button");
      name.type = "button";
      name.className = "product-title";
      const titleText = document.createElement("span");
      titleText.className = "title-text";
      titleText.textContent = product.name;
      name.append(titleText);
      name.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        this._showNameTooltip(name, product.name);
      });
      if (product.image_url) {
        const image = document.createElement("img");
        image.className = "product-image";
        image.src = product.image_url;
        image.alt = "";
        image.loading = "lazy";
        image.decoding = "async";
        image.referrerPolicy = "no-referrer";
        image.addEventListener("error", () => image.remove(), { once: true });
        image.classList.add("image-preview-anchor");
        this._bindImagePreview(image, image, product.name);
        selectionLabel.append(checkbox, image);
      } else {
        selectionLabel.append(checkbox);
      }
      const quantityControl = document.createElement("div");
      quantityControl.className = "picker-quantity-control";
      const decrease = document.createElement("ha-icon-button");
      decrease.path = "M19 13H5v-2h14v2Z";
      decrease.setAttribute("aria-label", this._strings().decreaseQuantity(product.name));
      decrease.disabled = true;
      decrease.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        this._changePickerQuantity(row, -1);
      });
      const quantityValue = document.createElement("span");
      quantityValue.className = "picker-quantity-value";
      quantityValue.textContent = "1";
      const increase = document.createElement("ha-icon-button");
      increase.path = "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2Z";
      increase.setAttribute("aria-label", this._strings().increaseQuantity(product.name));
      increase.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        this._changePickerQuantity(row, 1);
      });
      quantityControl.append(decrease, quantityValue, increase);
      row.dataset.unitPrice = product.unit_price ?? "";
      row.dataset.formattedPrice = product.formatted_price || "";
      row.dataset.regularPrice = product.regular_price ?? "";
      row.dataset.formattedRegularPrice = product.formatted_regular_price || "";
      row.dataset.bundleBuyQuantity = product.bundle_buy_quantity ?? "";
      row.dataset.bundleFreeQuantity = product.bundle_free_quantity ?? "";
      row.dataset.discountPercent = product.discount_percent ?? "";
      row.dataset.discountMinQuantity = product.discount_min_quantity ?? "";
      row.dataset.promotions = JSON.stringify(product.promotions || []);
      const info = document.createElement("div");
      info.className = "product-info";
      info.append(name);
      productName.append(selectionLabel, info);
      row.append(productName, quantityControl);
      results.append(row);
      this._updateProductRow(row);
    }
    if (products.length && !append) {
      this.shadowRoot.querySelector("#picker").showModal();
    }
    this._updatePickerTotal();
  }

  _formatMoney(value) {
    return new Intl.NumberFormat(this._language() === "el" ? "el-GR" : "en-US", {
      style: "currency",
      currency: "EUR",
    }).format(Number(value));
  }

  _pickerQuantity(row) {
    return Math.max(1, Math.min(99, Number(row.querySelector(".picker-quantity-value")?.textContent) || 1));
  }

  _changePickerQuantity(row, delta) {
    const value = row.querySelector(".picker-quantity-value");
    const quantity = Math.max(1, Math.min(99, this._pickerQuantity(row) + delta));
    value.textContent = String(quantity);
    const buttons = row.querySelectorAll(".picker-quantity-control ha-icon-button");
    buttons[0].disabled = quantity <= 1;
    buttons[1].disabled = quantity >= 99;
    this._updateProductRow(row);
    this._updatePickerTotal();
  }

  _updateProductRow(row) {
    const details = row.querySelector(".product-details") || document.createElement("div");
    details.className = "product-details";
    const price = row.dataset.unitPrice ? Number(row.dataset.unitPrice) : Number.NaN;
    const quantity = this._pickerQuantity(row);
    if (Number.isFinite(price)) {
      const buyQuantity = Number(row.dataset.bundleBuyQuantity) || 0;
      const freeQuantity = Number(row.dataset.bundleFreeQuantity) || 0;
      const offerSize = buyQuantity + freeQuantity;
      const paidQuantity = offerSize > 0
        ? quantity - Math.floor(quantity / offerSize) * freeQuantity
        : quantity;
      const total = this._calculateProductTotal(row, quantity);
      const discountMinQuantity = Number(row.dataset.discountMinQuantity) || 1;
      const currentLabel = discountMinQuantity > 1
        ? this._strings().quantityTotal(this._formatMoney(total))
        : quantity > 1
          ? `${this._formatMoney(price)} × ${paidQuantity} = ${this._formatMoney(total)}`
          : this._formatMoney(total);
      const regularPrice = row.dataset.regularPrice ? Number(row.dataset.regularPrice) : Number.NaN;
      details.replaceChildren();
      if (
        !offerSize
        && Number.isFinite(regularPrice)
        && total < regularPrice * quantity
      ) {
        const oldPrice = document.createElement("del");
        oldPrice.textContent = row.dataset.formattedRegularPrice || this._formatMoney(regularPrice);
        details.append(oldPrice, document.createTextNode(" "));
      }
      details.append(document.createTextNode(currentLabel));
    } else {
      details.textContent = this._strings().priceUnavailable;
    }
    const info = row.querySelector(".product-info");
    if (!details.parentElement) info.append(details);
    const promoNode = row.querySelector(".product-promotion");
    let promotions = [];
    try { promotions = JSON.parse(row.dataset.promotions || "[]"); } catch {}
    const promotionText = promotions
      .map((promotion) => promotion.title || promotion.description)
      .filter(Boolean)
      .join(" · ");
    if (promotionText) {
      const offer = promoNode || document.createElement("div");
      offer.className = "product-promotion";
      offer.textContent = promotionText;
      if (!promoNode) info.append(offer);
    } else if (promoNode) {
      promoNode.remove();
    }
  }

  _updatePickerTotal() {
    const totalNode = this.shadowRoot.querySelector("#picker-total");
    const statusNode = this.shadowRoot.querySelector("#picker-status");
    if (!totalNode || !statusNode) return;
    const selected = [...this.shadowRoot.querySelectorAll(".product")]
      .filter((row) => row.querySelector(".product-checkbox")?.checked);
    if (!selected.length) {
      totalNode.textContent = "";
      totalNode.hidden = true;
      if (this._selectionRequired) {
        statusNode.textContent = this._strings().selectProduct;
        statusNode.classList.add("error");
      }
      statusNode.hidden = !this._selectionRequired;
      return;
    }
    this._selectionRequired = false;
    totalNode.hidden = false;
    statusNode.textContent = "";
    statusNode.hidden = true;
    statusNode.classList.remove("error");
    const prices = selected.map((row) => row.dataset.unitPrice ? Number(row.dataset.unitPrice) : Number.NaN);
    if (prices.some((price) => !Number.isFinite(price))) {
      totalNode.textContent = "";
      totalNode.hidden = true;
    } else {
      const total = selected.reduce((sum, row) => {
        const quantity = this._pickerQuantity(row);
        return sum + this._calculateProductTotal(row, quantity);
      }, 0);
      totalNode.textContent = this._strings().selectedTotal(this._formatMoney(total));
    }
  }

  _calculateProductTotal(row, quantity) {
    const unitPrice = Number(row.dataset.unitPrice);
    const buyQuantity = Number(row.dataset.bundleBuyQuantity) || 0;
    const freeQuantity = Number(row.dataset.bundleFreeQuantity) || 0;
    const offerSize = buyQuantity + freeQuantity;
    if (offerSize > 0) {
      const paidQuantity = quantity - Math.floor(quantity / offerSize) * freeQuantity;
      return Math.round(unitPrice * paidQuantity * 100) / 100;
    }

    const percentage = Number(row.dataset.discountPercent);
    if (Number.isFinite(percentage) && percentage > 0) {
      const regularPrice = Number(row.dataset.regularPrice);
      const basePrice = Number.isFinite(regularPrice) ? regularPrice : unitPrice;
      const threshold = Math.max(1, Number(row.dataset.discountMinQuantity) || 1);
      const discountedQuantity = Math.floor(quantity / threshold) * threshold;
      const regularQuantity = quantity - discountedQuantity;
      const discountedUnitCents = Math.round(Math.round(basePrice * 100) * (100 - percentage) / 100);
      const regularUnitCents = Math.round(basePrice * 100);
      return (discountedUnitCents * discountedQuantity + regularUnitCents * regularQuantity) / 100;
    }
    return Math.round(unitPrice * quantity * 100) / 100;
  }

  async _addSelected() {
    const selected = [...this.shadowRoot.querySelectorAll(".product")]
      .map((row) => ({
        checkbox: row.querySelector(".product-checkbox"),
        quantity: this._pickerQuantity(row),
      }))
      .filter(({ checkbox }) => checkbox.checked)
      .map(({ checkbox, quantity }) => ({
        code: checkbox.dataset.code,
        name: checkbox.dataset.name,
        quantity,
      }));
    if (!selected.length) {
      this._selectionRequired = true;
      this._updatePickerTotal();
      return;
    }

    const button = this.shadowRoot.querySelector("#add");
    const status = this.shadowRoot.querySelector("#status");
    const pickerStatus = this.shadowRoot.querySelector("#picker-status");
    const text = this._strings();
    pickerStatus.textContent = "";
    pickerStatus.classList.remove("error");
    pickerStatus.hidden = true;
    button.disabled = true;
    try {
      await this._hass.callService("ab_vassilopoulos", "add_products", {
        entity_id: this._config?.todo_entity,
        products: selected,
      });
      this.shadowRoot.querySelector("#picker").close();
      const totalQuantity = selected.reduce((total, product) => total + product.quantity, 0);
      status.textContent = text.added(totalQuantity);
    } catch (error) {
      pickerStatus.textContent = error?.message || text.addFailed;
      pickerStatus.classList.add("error");
      pickerStatus.hidden = false;
      this.shadowRoot.querySelector("#picker-total").hidden = true;
    } finally {
      button.disabled = false;
    }
  }

  getCardSize() {
    return 6;
  }
}

// Home Assistant can replace window.customElements while its scoped-registry
// polyfill initializes. Wait until the application element is registered in
// the active registry before registering this card, so the definition survives.
let registrationAttempts = 0;
const registerABProductPickerCard = () => {
  const registry = window.customElements;
  if (!registry?.get("home-assistant")) {
    if (registrationAttempts++ < 200) {
      window.setTimeout(registerABProductPickerCard, 50);
    } else {
      console.error("AB product picker could not find the active Home Assistant element registry.");
    }
    return;
  }
  if (!registry.get("ab-product-picker-card")) {
    registry.define("ab-product-picker-card", ABProductPickerCard);
  }
};
registerABProductPickerCard();
window.customCards = window.customCards || [];
const cardIsGreek = (document.documentElement.lang || "en").toLowerCase().startsWith("el");
window.customCards.push({
  type: "ab-product-picker-card",
  name: cardIsGreek ? "Επιλογή προϊόντων ΑΒ" : "AB product picker",
  description: cardIsGreek
    ? "Αναζήτηση προϊόντων ΑΒ και προσθήκη επιλεγμένων στο καλάθι."
    : "Search AB products and add selected items to the cart.",
});
