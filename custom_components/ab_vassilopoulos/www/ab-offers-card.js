class ABOffersCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._requestId = 0;
    this._page = 0;
    this._pageSize = 10;
    this._offerFetchPageSize = 40;
    this._offersCacheTtl = 30 * 60 * 1000;
    this._offerProducts = [];
    this._nextOfferApiPage = 0;
    this._offerApiTotalPages = 0;
    this._offerTotalResults = 0;
    this._sortMode = "default";
    this._selectedCategoryCode = "default";
    this._categories = [];
    this._query = "promotions:relevance";
    this._quantities = new Map();
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "title", selector: { text: {} } },
        { name: "todo_entity", selector: { entity: { filter: { integration: "ab_vassilopoulos", domain: "todo" } } } },
      ],
      computeLabel: (field) => ({
        title: document.documentElement.lang?.startsWith("el") ? "Τίτλος" : "Title",
        todo_entity: document.documentElement.lang?.startsWith("el") ? "Λογαριασμός ΑΒ / λίστα καλαθιού" : "AB account / shopping list",
      })[field.name],
    };
  }

  static getStubConfig() { return {}; }

  setConfig(config) {
    const previousEntity = this._config?.todo_entity || null;
    this._config = { ...config };
    if (previousEntity !== (this._config.todo_entity || null)) {
      this._requestId += 1;
      this._data = null;
      this._offerProducts = [];
      this._nextOfferApiPage = 0;
      this._offerApiTotalPages = 0;
      this._offerTotalResults = 0;
      this._quantities.clear();
      this._categories = [];
      this._selectedCategoryCode = "default";
      this._sortMode = "default";
    }
    this._build();
    this._load(true);
  }

  set hass(hass) {
    this._hass = hass;
    this._updateCardTitle();
    const state = hass.states[this._todoEntity()];
    if (state !== this._lastTodoState) {
      this._lastTodoState = state;
      this._page = 0;
      this._renderProducts();
      if (this._data) this._renderStatus();
    }
    if (this._language !== this._getLanguage()) {
      this._language = this._getLanguage();
      this._build();
      this._renderProducts();
      if (this._data) {
        this._renderStatus();
      }
    }
    if (!this._data && !this._loadStarted) {
      this._loadStarted = true;
      this._load(true);
    }
  }

  _getLanguage() {
    return (this._hass?.language || document.documentElement.lang || "en").toLowerCase().startsWith("el") ? "el" : "en";
  }

  _text() {
    return this._getLanguage() === "el" ? {
      title: "Προσφορές ΑΒ", loading: "Φόρτωση προσφορών…", failed: "Δεν ήταν δυνατή η φόρτωση προσφορών.",
      selectAccount: "Επίλεξε λογαριασμό ΑΒ στις ρυθμίσεις της κάρτας.",
      none: "Δεν βρέθηκαν προσφορές.", retry: "Δοκιμή ξανά",
      add: "Προσθήκη", adding: "Προσθήκη…", added: "Προστέθηκε", addFailed: "Αποτυχία προσθήκης",
      previous: "Προηγούμενη", next: "Επόμενη", page: (p, n, total) => `Σελίδα ${p} από ${n} · ${total} προϊόντα`,
      decrease: "Μείωση ποσότητας", increase: "Αύξηση ποσότητας",
      sort: "Ταξινόμηση", defaultOrder: "Όλα τα προϊόντα", categoryOrder: "Κατηγορίες", categoriesUnavailable: "Δεν βρέθηκαν κατηγορίες προσφορών από τον ΑΒ.",
    } : {
      title: "AB offers", loading: "Loading offers…", failed: "Could not load offers.", none: "No offers found.",
      selectAccount: "Select an AB account in card settings.",
      retry: "Retry", add: "Add", adding: "Adding…", added: "Added",
      addFailed: "Add failed", previous: "Previous", next: "Next",
      page: (p, n, total) => `Page ${p} of ${n} · ${total} products`,
      decrease: "Decrease quantity", increase: "Increase quantity",
      sort: "Sort by", defaultOrder: "All products", categoryOrder: "Categories", categoriesUnavailable: "AB did not return offer categories.",
    };
  }

  _todoEntity() { return this._config.todo_entity || null; }

  _accountName() {
    const friendlyName = String(
      this._hass?.states[this._todoEntity()]?.attributes?.friendly_name || "",
    ).trim();
    const account = friendlyName.match(/\(([^()]*)\)\s*$/);
    return account?.[1]?.trim() || friendlyName;
  }

  _resolvedCardTitle() {
    const customTitle = String(this._config?.title || "").trim();
    if (customTitle) return customTitle;
    const account = this._accountName();
    if (account) return `${this._getLanguage() === "el" ? "Προσφορές" : "Offers"} · ${account}`;
    return this._text().title;
  }

  _updateCardTitle() {
    const title = this.shadowRoot?.querySelector(".head h1");
    if (title) title.textContent = this._resolvedCardTitle();
  }

  _build() {
    if (!this._config) return;
    const t = this._text();
    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block} ha-card{overflow:hidden}.content{padding:16px}
        .head{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:40px;margin-bottom:8px}
        .head ha-select{flex:0 0 180px;width:180px;--mdc-menu-min-width:180px;--mdc-typography-subtitle1-font-size:var(--ha-font-size-s)}
        h1{color:var(--ha-card-header-color,var(--primary-text-color));font-family:var(--ha-card-header-font-family,inherit);font-size:var(--ha-card-header-font-size,var(--ha-font-size-2xl,1.5rem));font-weight:var(--ha-font-weight-normal,400);letter-spacing:-.012em;line-height:var(--ha-line-height-condensed,1.2);margin:0}
                .status{min-height:1.5em;color:var(--secondary-text-color);font-size:var(--ha-font-size-s);margin:4px 0 8px}
        .products{border-top:1px solid var(--divider-color);border-bottom:1px solid var(--divider-color)}
        .category-heading{padding:7px 0 4px;border-bottom:1px solid var(--divider-color);color:var(--primary-text-color);font-size:var(--ha-font-size-m);font-weight:var(--ha-font-weight-medium,500)}
        .product{display:flex;align-items:center;gap:12px;min-height:48px;padding:4px 0;border-bottom:1px solid var(--divider-color);box-sizing:border-box}
        .product:last-child{border-bottom:0}.image-anchor{display:grid;place-items:center;width:40px;height:40px;flex:0 0 40px;padding:0;border:0;background:transparent;color:inherit;cursor:zoom-in}
        .image{display:block;width:100%;height:100%;object-fit:contain;border-radius:4px}.info{display:grid;gap:3px;min-width:0;flex:1}
        .title-line{display:flex;align-items:baseline;gap:6px;min-width:0}.name{appearance:none;display:block;flex:1;min-width:0;width:auto;min-height:0;padding:0;border:0;border-radius:0;background:transparent;color:var(--primary-text-color);font:inherit;font-weight:inherit;line-height:1.4em;text-align:left;cursor:pointer}.title-text{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;line-clamp:2;overflow:hidden;text-overflow:ellipsis;overflow-wrap:anywhere;white-space:normal;width:100%;min-width:0;max-width:100%;box-sizing:border-box}
        .price{font-size:var(--ha-font-size-s);font-variant-numeric:tabular-nums;line-height:1.3}.old{color:var(--secondary-text-color);text-decoration:line-through;margin-inline-end:6px;font-size:.9em}
        .promo{font-size:var(--ha-font-size-s);line-height:1.3;cursor:pointer;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:1;overflow:hidden}
        .promo{color:var(--success-color,#2e7d32)}.name.previously-purchased{color:var(--primary-color)}
        .controls{display:flex;align-items:center;gap:2px;flex:0 0 auto}.controls ha-icon-button{--mdc-icon-button-size:36px;--mdc-icon-size:20px}
        .qty{min-width:2ch;text-align:center;font-variant-numeric:tabular-nums}
        button{font:inherit;color:var(--primary-text-color);background:var(--secondary-background-color);border:1px solid var(--divider-color);border-radius:var(--ha-button-border-radius,6px);min-height:36px;padding:5px 9px;cursor:pointer}
        button:disabled{opacity:.5;cursor:default}.add{flex:0 0 auto;white-space:nowrap}
        .pager{display:flex;justify-content:center;align-items:center;gap:12px;min-height:48px;padding-top:8px}
        .pager[hidden]{display:none}.pager ha-button{min-width:104px}.page-label{min-width:7ch;text-align:center;font-size:var(--ha-font-size-s);color:var(--secondary-text-color)}
        #retry{display:block;margin:0 auto 8px;color:var(--primary-color);background:transparent;border:0}#retry[hidden]{display:none}
        .tooltip{position:fixed;z-index:10000;max-width:min(340px,calc(100vw - 24px));max-height:45vh;overflow:auto;box-sizing:border-box;padding:10px 12px;border-radius:8px;color:var(--primary-text-color);background:var(--card-background-color);box-shadow:0 4px 18px #0005;font:var(--ha-font-size-m,14px)/1.4 var(--ha-font-family-body,Roboto,sans-serif);white-space:normal;overflow-wrap:anywhere;pointer-events:auto;width:max-content}
        .tooltip[hidden]{display:none}.tooltip.image-tooltip{width:auto!important;max-width:min(75vw,420px);max-height:60vh;padding:6px;overflow:hidden}
        .tooltip.image-tooltip img{display:block;width:auto;height:auto;max-width:min(75vw,420px);max-height:60vh;object-fit:contain;border-radius:4px}
        @media(max-width:480px){.content{padding:12px}.product{gap:12px}.image-anchor{width:40px;height:40px;flex-basis:40px}.add{font-size:var(--ha-font-size-s)}.controls ha-icon-button{--mdc-icon-button-size:32px}.pager ha-button{min-width:88px}}
      </style>
      <ha-card><div class="content">
        <div class="head"><h1>${this._esc(this._resolvedCardTitle())}</h1><ha-select id="sort-select"></ha-select></div>
        <div id="status" class="status" role="status">${this._esc(t.loading)}</div>
        <button id="retry" hidden>${this._esc(t.retry)}</button>
        <div id="products" class="products"></div>
        <div id="pager" class="pager">
          <ha-button id="previous" appearance="plain">${this._esc(t.previous)}</ha-button><span id="page-label" class="page-label"></span><ha-button id="next" appearance="plain">${this._esc(t.next)}</ha-button>
        </div>
      </div></ha-card><div id="offer-tooltip" class="tooltip" role="tooltip" hidden></div>`;

    this._setCategoryOptions();
    this.shadowRoot.querySelector("#previous").addEventListener("click", () => {
      if (this._page > 0) { this._page -= 1; this._renderProducts(); this._renderStatus(); }
    });
    this.shadowRoot.querySelector("#next").addEventListener("click", () => {
      if (this._page + 1 < this._totalPages) { this._page += 1; this._renderProducts(); this._renderStatus(); }
    });
    this.shadowRoot.querySelector("#retry").addEventListener("click", () => this._load(false));
    const sortSelect = this.shadowRoot.querySelector("#sort-select");
    sortSelect.addEventListener("selected", (event) => {
      const selected = String(event.detail?.value || "default");
      const category = this._categories.find((item) => item.code === selected);
      if (selected !== "default" && !category) return;
      this._selectedCategoryCode = selected;
      this._sortMode = category ? "category" : "default";
      sortSelect.value = selected;
      this._page = 0;
      this._data = null;
      this._load(true);
    });
    const tooltip = this.shadowRoot.querySelector("#offer-tooltip");
    tooltip.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      this._hideTooltip();
    });
    if (!this._tooltipListenersBound) {
      window.addEventListener("scroll", () => this._hideTooltip(), true);
      window.addEventListener("pointerdown", (event) => {
        if (!this._activeTooltip || this._activeTooltip.hidden) return;
        const path = event.composedPath();
        if (!path.includes(this._activeTooltip) && !path.includes(this._activeTooltipTarget)) this._hideTooltip();
      }, true);
      this._tooltipListenersBound = true;
    }
  }

  _esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" })[ch]);
  }

  _updateCategories(facets) {
    const categoryFacet = (facets || []).find((facet) => /category|κατηγ/i.test(`${facet.code || ""} ${facet.name || ""} ${facet.category || ""}`));
    const categories = (categoryFacet?.values || [])
      .filter((value) => value?.name && (value.search_query || value.code != null) && Number(value.count ?? 1) > 0)
      .map((value) => ({ code: String(value.code ?? value.search_query), name: String(value.name), query: String(value.search_query || "") }));
    if (!categories.length) return;
    this._categories = categories;
    this._setCategoryOptions();
  }

  _setCategoryOptions() {
    const select = this.shadowRoot?.querySelector("#sort-select");
    if (!select) return;
    const text = this._text();
    select.label = text.categoryOrder;
    select.options = [
      { value: "default", label: text.defaultOrder },
      ...this._categories.map((category) => ({ value: category.code, label: category.name })),
    ];
    select.value = this._selectedCategoryCode || "default";
  }

  async _load(reset) {
    if (!this._hass || !this.shadowRoot?.querySelector("#status")) return;
    const status = this.shadowRoot.querySelector("#status");
    const products = this.shadowRoot.querySelector("#products");
    const retry = this.shadowRoot.querySelector("#retry");
    const pager = this.shadowRoot.querySelector("#pager");
    if (!this._todoEntity()) {
      this._data = null;
      this._offerProducts = [];
      products.replaceChildren();
      retry.hidden = true;
      pager.hidden = true;
      status.textContent = this._text().selectAccount;
      return;
    }
    pager.hidden = false;
    if (reset) {
      this._page = 0;
      this._query = this._categories.find((category) => category.code === this._selectedCategoryCode)?.query || "promotions:relevance";
      const cached = this._readOffersCache();
      if (cached) {
        this._offerProducts = cached.products;
        this._categories = Array.isArray(cached.categories) ? cached.categories : this._categories;
        this._setCategoryOptions();
        this._categoryOrder = [...new Map(cached.products.filter((product) => product.offer_category_code).map((product) => [product.offer_category_code, product.offer_category_name])).entries()].map(([code, name]) => ({ code, name }));
        // The AB API's totalResults is not always the number of distinct
        // products returned by pagination. Trust the cached product list.
        this._offerTotalResults = cached.products.length;
        this._offerApiTotalPages = cached.api_total_pages;
        this._nextOfferApiPage = this._offerApiTotalPages;
        this._data = { products: this._offerProducts, total_results: this._offerProducts.length, total_pages: Math.ceil(this._offerProducts.length / this._pageSize) };
        this._totalPages = Math.max(1, this._data.total_pages || 1);
        this._renderProducts();
        this._renderStatus();
        if (Date.now() - cached.saved_at < this._offersCacheTtl) return;
      }
      this._offerProducts = [];
      this._nextOfferApiPage = 0;
      this._offerApiTotalPages = 0;
      this._offerTotalResults = 0;
    }
    this._hideTooltip();
    const id = ++this._requestId;
    if (!this._data) status.textContent = this._text().loading;
    retry.hidden = true;
    if (!this._data) products.replaceChildren();
    try {
      const selectedCategory = this._categories.find((category) => category.code === this._selectedCategoryCode);
      const searchQuery = selectedCategory?.query || "promotions:relevance";
      while (this._nextOfferApiPage < 200) {
        const result = await this._hass.callWS({
          type: "call_service", domain: "ab_vassilopoulos", service: "get_offers",
          service_data: {
            search_query: searchQuery, page: this._nextOfferApiPage, page_size: this._offerFetchPageSize,
            entity_id: this._todoEntity(),
            include_unavailable: false, language: this._getLanguage(), ...(selectedCategory?.query ? {} : selectedCategory ? { category_code: selectedCategory.code } : {}),
          },
          return_response: true,
        });
        if (id !== this._requestId) return;
        const data = result?.response || result;
        if (this._nextOfferApiPage === 0 && !selectedCategory) this._updateCategories(data?.facets);
        const batch = Array.isArray(data?.products) ? data.products : [];
        this._offerTotalResults = Number(data?.total_results ?? this._offerTotalResults ?? 0);
        const knownCodes = new Set(this._offerProducts.map((product) => String(product.code)));
        const previousCount = this._offerProducts.length;
        for (const product of batch) {
          const code = String(product.code);
          if (!knownCodes.has(code)) {
            knownCodes.add(code);
            this._offerProducts.push(selectedCategory ? { ...product, offer_category_code: selectedCategory.code, offer_category_name: selectedCategory.name } : product);
          }
        }
        this._offerApiTotalPages = Math.max(Number(data?.total_pages || 0), Math.ceil(this._offerTotalResults / this._offerFetchPageSize));
        this._nextOfferApiPage += 1;
        // Continue until the API stops yielding new products. Its count can
        // be stale/overcounted and must not truncate the actual result set.
        if (!batch.length || (
          this._nextOfferApiPage >= this._offerApiTotalPages &&
          this._offerProducts.length === previousCount
        )) break;
        if (this._nextOfferApiPage < this._offerApiTotalPages) await new Promise((resolve) => window.setTimeout(resolve, 200));
      }
      if (id !== this._requestId) return;
      this._offerTotalResults = this._offerProducts.length;
      this._data = { products: this._offerProducts, total_results: this._offerProducts.length, total_pages: Math.ceil(this._offerProducts.length / this._pageSize) };
      this._totalPages = Math.max(1, this._data.total_pages || 1);
      this._renderProducts();
      this._renderStatus();
      this._writeOffersCache();
    } catch (error) {
      if (id !== this._requestId) return;
      console.error("AB offers load/render failed:", error);
      status.textContent = `${this._text().failed} ${error?.message || ""}`;
      retry.hidden = false;
      this.shadowRoot.querySelector("#pager").hidden = false;
      this.shadowRoot.querySelector("#previous").disabled = true;
      this.shadowRoot.querySelector("#next").disabled = true;
      this.shadowRoot.querySelector("#page-label").textContent = "–";
    }
  }

  _offersCacheKey() { return `ab-offers:v24:${this._todoEntity()}:${this._getLanguage()}:${this._sortMode}:${this._query}`; }

  _readOffersCache() {
    try {
      const value = JSON.parse(window.sessionStorage.getItem(this._offersCacheKey()) || "null");
      if (!Array.isArray(value?.products) || !Number.isFinite(value.saved_at)) return null;
      return value;
    } catch (_) { return null; }
  }

  _writeOffersCache() {
    try {
      window.sessionStorage.setItem(this._offersCacheKey(), JSON.stringify({
        saved_at: Date.now(), products: this._offerProducts,
        total_results: this._offerTotalResults, api_total_pages: this._offerApiTotalPages, categories: this._categories,
      }));
    } catch (_) { /* Storage can be unavailable in private browsing. */ }
  }

  _renderStatus() {
    if (!this._data) return;
    const count = Number(this._data.total_results || 0);
    const totalPages = Math.max(1, Number(this._totalPages || 1));
    const text = this._text();
    this.shadowRoot.querySelector("#status").textContent = count ? text.page(this._page + 1, totalPages, count) : text.none;
    const pager = this.shadowRoot.querySelector("#pager");
    pager.hidden = false;
    this.shadowRoot.querySelector("#page-label").textContent = `${this._page + 1} / ${totalPages}`;
    this.shadowRoot.querySelector("#previous").disabled = this._page <= 0;
    this.shadowRoot.querySelector("#next").disabled = this._page + 1 >= totalPages;
  }

  _formatMoney(value) {
    return new Intl.NumberFormat(this._getLanguage() === "el" ? "el-GR" : "en-US", { style: "currency", currency: "EUR" }).format(Number(value));
  }

  _promotionDeal(item) {
    const promotions = Array.isArray(item.promotions) ? item.promotions : [];
    const normalize = (value) => String(value || "")
      .replace(/<[^>]*>/g, " ")
      .replace(/&nbsp;|&#160;|&#xA0;/gi, " ")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase()
      .replace(/\s+/g, " ")
      .trim();
    const parseThreshold = (text) => {
      const patterns = [
        /(?:στα|στο|στη|στην|στις|στους|στες|σε|για|με|at|on|off|with)\s*(\d+)(?!\d)/,
        /(?:αγορα(?:σε|ς|ζοντας)?|buy(?:ing)?|purchase(?:\s+of)?)\s*(\d+)(?!\d)/,
        /(?:^|\s)(\d+)\s*προιον(?:\(τα\)|τα)?(?!\p{L})/u,
        /(?:^|\s)(\d+)\s*(?:τεμαχια|τεμ\.?|τμχ\.?|items?|products?)(?!\p{L})/u,
      ];
      for (const pattern of patterns) {
        const quantity = Number(text.match(pattern)?.[1]);
        if (quantity > 1 && quantity <= 99) return quantity;
      }
      return 1;
    };
    const combinedText = normalize(promotions.map((promotion) => `${promotion.title || ""} ${promotion.description || ""} ${promotion.promotionType || ""}`).join(" "));
    const combinedThreshold = parseThreshold(combinedText);
    let firstPercentage = null;
    for (const promotion of promotions) {
      const text = normalize(`${promotion.title || ""} ${promotion.description || ""} ${promotion.promotionType || ""}`);
      const percentMatch = text.match(/(\d+(?:[.,]\d+)?)\s*%/);
      if (!percentMatch) continue;
      const candidate = {
        percent: Number(percentMatch[1].replace(",", ".")),
        threshold: Math.max(parseThreshold(text), combinedThreshold),
      };
      if (candidate.percent <= 0 || candidate.percent > 100) continue;
      if (candidate.threshold > 1) return candidate;
      if (!firstPercentage) firstPercentage = candidate;
    }
    const backendPercent = Number(item.discount_percent);
    const backendThreshold = Number(item.discount_min_quantity);
    if (firstPercentage) {
      if (firstPercentage.threshold === 1 && backendThreshold > 1 && backendThreshold <= 99) {
        firstPercentage.threshold = backendThreshold;
      }
      return firstPercentage;
    }
    return {
      percent: backendPercent > 0 && backendPercent <= 100 ? backendPercent : 0,
      threshold: backendThreshold > 1 && backendThreshold <= 99 ? backendThreshold : 1,
    };
  }
  _quantityTotalPrice(item, qty) {
    const unitPrice = Number(item.unit_price);
    if (!Number.isFinite(unitPrice)) return Number(item.total_price);
    const buyQuantity = Number(item.bundle_buy_quantity) || 0;
    const freeQuantity = Number(item.bundle_free_quantity) || 0;
    const offerSize = buyQuantity + freeQuantity;
    if (offerSize > 0) {
      const paidQuantity = qty - Math.floor(qty / offerSize) * freeQuantity;
      return Math.round(unitPrice * paidQuantity * 100) / 100;
    }
    const deal = this._promotionDeal(item);
    const percentage = deal.percent;
    if (percentage > 0) {
      const basePrice = Number(item.regular_price ?? unitPrice);
      const threshold = deal.threshold;
      const discountedQuantity = Math.floor(qty / threshold) * threshold;
      const discountedUnitCents = Math.round(Math.round(basePrice * 100) * (100 - percentage) / 100);
      return (discountedUnitCents * discountedQuantity + Math.round(basePrice * 100) * (qty - discountedQuantity)) / 100;
    }
    return Math.round(unitPrice * qty * 100) / 100;
  }

  _renderProductPrice(container, item, qty) {
    const unitPrice = Number(item.unit_price);
    if (!Number.isFinite(unitPrice)) {
      container.textContent = this._getLanguage() === "el" ? "Χωρίς τιμή" : "Price unavailable";
      return;
    }
    const buyQuantity = Number(item.bundle_buy_quantity) || 0;
    const freeQuantity = Number(item.bundle_free_quantity) || 0;
    const offerSize = buyQuantity + freeQuantity;
    const paidQuantity = offerSize > 0 ? qty - Math.floor(qty / offerSize) * freeQuantity : qty;
    const total = this._quantityTotalPrice(item, qty);
    const threshold = this._promotionDeal(item).threshold;
    container.replaceChildren();
    if (!offerSize && item.regular_price != null && Number(item.regular_price) * qty > total) {
      const old = document.createElement("del");
      old.className = "old";
      old.textContent = this._formatMoney(item.regular_price);
      container.append(old, document.createTextNode(" "));
    }
    const label = threshold > 1
      ? `${this._getLanguage() === "el" ? "Σύνολο" : "Total"}: ${this._formatMoney(total)}`
      : qty > 1
        ? `${this._formatMoney(unitPrice)} × ${paidQuantity} = ${this._formatMoney(total)}`
        : this._formatMoney(total);
    container.append(document.createTextNode(label));
  }
  _renderProducts() {
    if (!this._data || !this.shadowRoot.querySelector("#products")) return;
    const container = this.shadowRoot.querySelector("#products");
    container.replaceChildren();
    const completedCodes = new Set((this._hass?.states[this._todoEntity()]?.attributes?.ab_items || [])
      .filter((item) => item.status === "completed")
      .map((item) => String(item.uid)));
    const orderedProducts = [...(this._offerProducts || [])];
    const categoryPositions = new Map((this._categoryOrder || []).map((category, index) => [String(category.code), index]));
    orderedProducts.sort((a, b) => {
      if (this._sortMode === "category") {
        const categoryDifference = (categoryPositions.get(String(a.offer_category_code)) ?? 0) - (categoryPositions.get(String(b.offer_category_code)) ?? 0);
        if (categoryDifference) return categoryDifference;
      }
      return Number(completedCodes.has(String(b.code))) - Number(completedCodes.has(String(a.code)));
    });
    const pageStart = this._page * this._pageSize;
    const pageProducts = orderedProducts.slice(pageStart, pageStart + this._pageSize);
    let previousCategoryCode = null;
    for (const item of pageProducts) {
      if (this._sortMode === "category" && item.offer_category_code !== previousCategoryCode) {
        const heading = document.createElement("div");
        heading.className = "category-heading";
        heading.textContent = item.offer_category_name || "";
        container.append(heading);
        previousCategoryCode = item.offer_category_code;
      }
      const row = document.createElement("div"); row.className = "product";
      const imageButton = document.createElement("button"); imageButton.type = "button"; imageButton.className = "image-anchor";
      const image = document.createElement("img"); image.className = "image"; image.loading = "lazy"; image.decoding = "async"; image.referrerPolicy = "no-referrer"; image.alt = "";
      image.src = item.image_url || "";
      if (!item.image_url) imageButton.hidden = true;
      image.addEventListener("error", () => { imageButton.hidden = true; }, { once: true });
      imageButton.append(image);
      imageButton.setAttribute("aria-label", item.name || "Product image");
      imageButton.addEventListener("click", (event) => { event.preventDefault(); event.stopPropagation(); this._showImageTooltip(imageButton, image); });
      row.append(imageButton);

      const info = document.createElement("div"); info.className = "info";
      const name = document.createElement("button"); name.type = "button"; name.className = "name";
      if (completedCodes.has(String(item.code))) name.classList.add("previously-purchased");
      const titleText = document.createElement("span"); titleText.className = "title-text"; titleText.textContent = item.name || ""; name.append(titleText);
      name.title = item.name || "";
      name.addEventListener("click", (event) => { event.preventDefault(); event.stopPropagation(); this._showNameTooltip(name, item.name || ""); });
      const titleLine = document.createElement("div"); titleLine.className = "title-line"; titleLine.append(name); info.append(titleLine);

      const itemQuantity = this._quantities.get(item.code) || 1;
      const promos = (item.promotions || []).map((offer) => offer.title || offer.description).filter(Boolean);
      const price = document.createElement("div"); price.className = "price";
      this._renderProductPrice(price, item, itemQuantity);
      info.append(price);
      if (promos.length) {
        const promo = document.createElement("div"); promo.className = "promo"; promo.textContent = promos.join(" · "); promo.title = promo.textContent;
        promo.setAttribute("role", "button"); promo.setAttribute("tabindex", "0");
        promo.addEventListener("click", (event) => { event.preventDefault(); event.stopPropagation(); this._showNameTooltip(promo, promo.textContent); });
        promo.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); this._showNameTooltip(promo, promo.textContent); } });
        info.append(promo);
      }
      row.append(info);

      const controls = document.createElement("div"); controls.className = "controls";
      const minus = document.createElement("ha-icon-button"); minus.path = "M19 13H5v-2h14v2Z"; minus.setAttribute("aria-label", `${this._text().decrease}: ${item.name}`); minus.disabled = itemQuantity <= 1;
      const count = document.createElement("span"); count.className = "qty"; count.textContent = String(itemQuantity);
      const plus = document.createElement("ha-icon-button"); plus.path = "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2Z"; plus.setAttribute("aria-label", `${this._text().increase}: ${item.name}`); plus.disabled = itemQuantity >= 99;
      minus.addEventListener("click", () => { this._quantities.set(item.code, Math.max(1, itemQuantity - 1)); this._renderProducts(); });
      plus.addEventListener("click", () => { this._quantities.set(item.code, Math.min(99, itemQuantity + 1)); this._renderProducts(); });
      controls.append(minus, count, plus);
      const add = document.createElement("ha-button"); add.setAttribute("appearance", "filled"); add.className = "add"; add.textContent = this._text().add;
      add.addEventListener("click", () => this._add(item, add)); controls.append(add);
      row.append(controls); container.append(row);
    }
  }

  _showNameTooltip(target, value) {
    if (this._activeTooltipTarget === target && !this._tooltip.hidden) { this._hideTooltip(); return; }
    this._activeTooltip = this.shadowRoot.querySelector("#offer-tooltip");
    this._activeTooltipTarget = target;
    const tooltip = this._activeTooltip;
    tooltip.classList.remove("image-tooltip");
    tooltip.replaceChildren(document.createTextNode(value));
    tooltip.style.width = `${Math.max(1, target.getBoundingClientRect().width)}px`;
    tooltip.hidden = false;
    const rect = target.getBoundingClientRect();
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - tooltip.offsetWidth - 8));
    const top = rect.top + tooltip.offsetHeight <= window.innerHeight - 8 ? rect.top : Math.max(8, rect.bottom - tooltip.offsetHeight);
    tooltip.style.left = `${left}px`; tooltip.style.top = `${top}px`;
    this._startTooltipTimer();
  }

  _showImageTooltip(target, image) {
    this._activeTooltip = this.shadowRoot.querySelector("#offer-tooltip");
    this._activeTooltipTarget = target;
    const tooltip = this._activeTooltip;
    const preview = document.createElement("img"); preview.src = image.currentSrc || image.src; preview.alt = image.alt || "";
    tooltip.replaceChildren(preview); tooltip.classList.add("image-tooltip"); tooltip.style.width = "auto"; tooltip.hidden = false;
    requestAnimationFrame(() => {
      const rect = target.getBoundingClientRect();
      const left = Math.max(8, Math.min(rect.left + (rect.width - tooltip.offsetWidth) / 2, window.innerWidth - tooltip.offsetWidth - 8));
      const top = Math.max(8, Math.min(rect.top + (rect.height - tooltip.offsetHeight) / 2, window.innerHeight - tooltip.offsetHeight));
      tooltip.style.left = `${left}px`; tooltip.style.top = `${top}px`;
    });
    this._startTooltipTimer();
  }

  _startTooltipTimer() {
    clearTimeout(this._tooltipTimer);
    this._tooltipTimer = window.setTimeout(() => this._hideTooltip(), 4000);
  }

  _hideTooltip() {
    if (this._activeTooltip) { this._activeTooltip.hidden = true; this._activeTooltip.classList.remove("image-tooltip"); this._activeTooltip.replaceChildren(); }
    this._activeTooltip = null; this._activeTooltipTarget = null; clearTimeout(this._tooltipTimer);
  }

  async _add(item, button) {
    const text = this._text(); const selectedQuantity = this._quantities.get(item.code) || 1;
    button.disabled = true; button.textContent = text.adding;
    try {
      await this._hass.callService("ab_vassilopoulos", "add_products", { entity_id: this._todoEntity(), products: [{ code: item.code, name: item.name, quantity: selectedQuantity }] });
      button.textContent = text.added;
    } catch (error) { button.textContent = error?.message || text.addFailed; }
    window.setTimeout(() => { if (button.isConnected) { button.textContent = text.add; button.disabled = false; } }, 2200);
  }

  getCardSize() { return 8; }
  getGridOptions() { return { columns: "full" }; }
}

let attempts = 0;
const registerABOffersCard = () => {
  const registry = window.customElements;
  if (!registry?.get("home-assistant")) {
    if (attempts++ < 200) window.setTimeout(registerABOffersCard, 50);
    else console.error("AB offers card could not find the active Home Assistant element registry.");
    return;
  }
  if (!registry.get("ab-offers-card")) registry.define("ab-offers-card", ABOffersCard);
};
registerABOffersCard();
window.customCards = window.customCards || [];
window.customCards.push({
  type: "ab-offers-card",
  name: (document.documentElement.lang || "en").toLowerCase().startsWith("el") ? "Προσφορές ΑΒ" : "AB offers",
  description: (document.documentElement.lang || "en").toLowerCase().startsWith("el") ? "Περιήγηση στις προσφορές της ΑΒ και προσθήκη προϊόντων στο καλάθι." : "Browse AB promotions and add products to the cart.",
});
