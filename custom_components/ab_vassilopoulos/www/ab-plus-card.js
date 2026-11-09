class ABPlusCard extends HTMLElement {
  constructor() {
    super();
    this._hideTimer = null;
    this._autoShowAttempted = false;
  }

  setConfig(config) {
    const previousEntity = this._config?.todo_entity || null;
    this._config = config || {};
    if (previousEntity !== (this._config.todo_entity || null)) {
      this._clearHideTimer();
      this._card = null;
      this._autoShowAttempted = false;
      this._loading = false;
    }
    this._render();
    this._maybeAutoShow();
  }

  set hass(hass) {
    this._hass = hass;
    this._updateCardTitle();
    const language = this._getLanguage();
    if (language !== this._language) {
      this._language = language;
      this._render();
    }
    this._maybeAutoShow();
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "title", selector: { text: {} } },
        { name: "todo_entity", selector: { entity: { filter: { integration: "ab_vassilopoulos", domain: "todo" } } } },
        { name: "theme", selector: { theme: {} } },
        { name: "auto_show", selector: { boolean: {} } },
        { name: "show_status", selector: { boolean: {} } },
        { name: "barcode_width", default: 360, description: { suggested_value: 360 }, selector: { number: { min: 220, max: 420, step: 20, mode: "slider" } } },
        { name: "barcode_height", default: 48, description: { suggested_value: 48 }, selector: { number: { min: 32, max: 80, step: 4, mode: "slider" } } },
        { name: "auto_hide_seconds", default: 0, description: { suggested_value: 0 }, selector: { number: { min: 0, max: 300, step: 15, mode: "slider" } } },
      ],
      computeLabel: (field) => ABPlusCard._editorLabels()[field.name],
    };
  }

  static _editorLabels() {
    const greek = (document.documentElement.lang || "en").toLowerCase().startsWith("el");
    return greek ? {
      title: "Τίτλος", theme: "Θέμα", auto_show: "Αυτόματη εμφάνιση κάρτας",
      show_status: "Εμφάνιση κατάστασης κάρτας",
      todo_entity: "Λογαριασμός ΑΒ / λίστα καλαθιού",
      barcode_width: "Πλάτος barcode", barcode_height: "Ύψος barcode",
      auto_hide_seconds: "Αυτόματη απόκρυψη (δευτερόλεπτα, 0 = ποτέ)",
    } : {
      title: "Title", theme: "Theme", auto_show: "Show card automatically",
      show_status: "Show card status",
      todo_entity: "AB account / shopping list",
      barcode_width: "Barcode width", barcode_height: "Barcode height",
      auto_hide_seconds: "Auto-hide after seconds (0 = never)",
    };
  }

  static getStubConfig() {
    return { show_status: true, barcode_width: 360, barcode_height: 48, auto_hide_seconds: 0 };
  }

  getGridOptions() {
    return { columns: "full" };
  }

  _getLanguage() {
    return (this._hass?.language || document.documentElement.lang || "en")
      .toLowerCase().startsWith("el") ? "el" : "en";
  }

  _text() {
    return this._getLanguage() === "el" ? {
      title: "Η AB Plus κάρτα μου", show: "Εμφάνιση κάρτας", hide: "Απόκρυψη κάρτας",
      selectAccount: "Επίλεξε λογαριασμό ΑΒ στις ρυθμίσεις της κάρτας.",
      loading: "Φόρτωση κάρτας…", error: "Δεν ήταν δυνατή η φόρτωση της κάρτας.",
      invalid: "Η μορφή του barcode δεν υποστηρίζεται.", cardLabel: "AB Plus",
      number: "Αριθμός κάρτας", status: "Κατάσταση κάρτας", retry: "Δοκιμή ξανά", cached: "Προβάλλεται το αποθηκευμένο barcode· δεν έγινε ανανέωση από τον ΑΒ.",
    } : {
      title: "My AB Plus card", show: "Show card", hide: "Hide card",
      selectAccount: "Select an AB account in card settings.",
      loading: "Loading card…", error: "Could not load the card.",
      invalid: "The barcode format is not supported.", cardLabel: "AB Plus",
      number: "Card number", status: "Card status", retry: "Retry", cached: "Showing the saved barcode; AB could not refresh it.",
    };
  }

  _accountName() {
    const friendlyName = String(
      this._hass?.states[this._config?.todo_entity]?.attributes?.friendly_name || "",
    ).trim();
    const account = friendlyName.match(/\(([^()]*)\)\s*$/);
    return account?.[1]?.trim() || friendlyName;
  }

  _resolvedCardTitle() {
    const customTitle = String(this._config?.title || "").trim();
    if (customTitle) return customTitle;
    const account = this._accountName();
    if (account) return `${this._getLanguage() === "el" ? "AB Plus" : "AB Plus"} · ${account}`;
    return this._text().title;
  }

  _updateCardTitle() {
    const title = this.shadowRoot?.querySelector(".title");
    if (title) title.textContent = this._resolvedCardTitle();
  }

  _maybeAutoShow() {
    if (this._config?.todo_entity && this._config?.auto_show && this._hass && !this._autoShowAttempted && !this._loading && !this._card) {
      this._autoShowAttempted = true;
      this._toggleCard();
    }
  }

  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const text = this._text();
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; color:var(--primary-text-color); font-family:var(--ha-font-family-body, Roboto, sans-serif); }
        ha-card { padding:16px; overflow:hidden; }
        .header { display:flex; align-items:center; justify-content:space-between; gap:12px; }
        .title { color:var(--ha-card-header-color,var(--primary-text-color)); font-family:var(--ha-card-header-font-family,inherit);
          font-size:var(--ha-card-header-font-size,var(--ha-font-size-2xl,1.5rem)); font-weight:var(--ha-font-weight-normal,400);
          letter-spacing:-.012em; line-height:var(--ha-line-height-condensed,1.2); min-width:0; }
        ha-button { flex:0 0 auto; }
        .status { margin-top:10px; color:var(--secondary-text-color); min-height:1.4em; }
        .status.error { color:var(--error-color); }
        .card { margin-top:12px; padding:16px; border-radius:12px; background:var(--primary-color); color:var(--text-primary-color, #fff); }
        .card-label { font-size:1.1rem; font-weight:600; margin-bottom:12px; }
        .barcode-wrap { display:flex; justify-content:center; padding:10px; background:#fff; border-radius:8px; margin:0 auto; }
        svg { display:block; width:100%; height:auto; }
        .card-status { margin-top:8px; text-align:center; color:var(--text-primary-color, #fff); font-size:var(--ha-font-size-m, 1rem); font-weight:500; }
        [hidden] { display:none !important; }
        @media (max-width:480px) { ha-card { padding:12px; } .header { align-items:flex-start; } }
      </style>
      <ha-card>
        <div class="header"><div class="title"></div><ha-button class="toggle" appearance="filled"></ha-button></div>
        <div class="status" role="status" aria-live="polite"></div>
        <div class="card" hidden>
          <div class="card-label"></div>
          <div class="barcode-wrap"></div>
          <div class="card-status"></div>
        </div>
      </ha-card>`;
    this.shadowRoot.querySelector(".title").textContent = this._resolvedCardTitle();
    const toggle = this.shadowRoot.querySelector(".toggle");
    toggle.textContent = this._card ? text.hide : text.show;
    toggle.disabled = !this._config.todo_entity;
    toggle.addEventListener("click", () => this._toggleCard());
    if (!this._config.todo_entity) this._setStatus(text.selectAccount);
    this._renderCard();
  }

  async _toggleCard() {
    if (this._card) {
      this._clearHideTimer();
      this._card = null;
      this._setStatus("");
      this._render();
      return;
    }
    if (!this._config.todo_entity) {
      this._setStatus(this._text().selectAccount);
      return;
    }
    if (!this._hass || this._loading) return;
    this._loading = true;
    const accountEntity = this._config.todo_entity;
    this._setStatus(this._text().loading);
    this.shadowRoot.querySelector(".toggle").disabled = true;
    try {
      const result = await this._hass.callWS({
        type: "call_service", domain: "ab_vassilopoulos", service: "get_loyalty_card",
        service_data: { entity_id: accountEntity }, return_response: true,
      });
      if (this._config.todo_entity !== accountEntity) return;
      this._card = result?.response || result;
      this._render();
      this._setStatus(this._card.cached ? this._text().cached : "");
      this._scheduleAutoHide();
    } catch (error) {
      const detail = String(error?.message || "").trim();
      const safeDetail = detail && detail.length < 180 ? ` ${detail}` : "";
      this._setStatus(`${this._text().error}${safeDetail}`, true);
      const button = this.shadowRoot.querySelector(".toggle");
      button.disabled = false;
      button.textContent = this._text().retry;
    } finally {
      this._loading = false;
    }
  }

  _scheduleAutoHide() {
    this._clearHideTimer();
    const seconds = Number(this._config.auto_hide_seconds || 0);
    if (seconds > 0 && this._card) {
      this._hideTimer = window.setTimeout(() => {
        this._card = null;
        this._setStatus("");
        this._render();
      }, seconds * 1000);
    }
  }

  _clearHideTimer() {
    if (this._hideTimer) window.clearTimeout(this._hideTimer);
    this._hideTimer = null;
  }

  _renderCard() {
    const panel = this.shadowRoot.querySelector(".card");
    const text = this._text();
    panel.hidden = !this._card;
    const toggle = this.shadowRoot.querySelector(".toggle");
    toggle.textContent = this._card ? text.hide : text.show;
    const status = this.shadowRoot.querySelector(".status");
    if (!this._config.show_status && !status.classList.contains("error") && this._config.todo_entity) status.hidden = true;
    if (!this._card) return;
    try {
      const number = String(this._card.card_number || "").replace(/\D/g, "");
      const width = this._boundedNumber("barcode_width", 360, 220, 420);
      const height = this._boundedNumber("barcode_height", 48, 32, 80);
      const barcode = this.shadowRoot.querySelector(".barcode-wrap");
      barcode.style.width = `min(100%, ${width}px)`;
      barcode.innerHTML = this._ean13Svg(number, height);
      const cardStatus = this.shadowRoot.querySelector(".card-status");
      const localizedStatus = Number(this._card.card_status_code) === 1 ? (this._getLanguage() === "el" ? "Ενεργή" : "Active") : this._card.card_status;
      cardStatus.textContent = localizedStatus ? `${text.status}: ${localizedStatus}` : "";
      cardStatus.hidden = this._config.show_status === false || !this._card.card_status;
      this.shadowRoot.querySelector(".card-label").textContent = text.cardLabel;
    } catch (error) {
      panel.hidden = true;
      this._card = null;
      this._setStatus(text.invalid, true);
    }
  }

  _boundedNumber(key, fallback, minimum, maximum) {
    const value = Number(this._config[key]);
    return Number.isFinite(value) ? Math.max(minimum, Math.min(maximum, value)) : fallback;
  }

  _setStatus(message, isError = false) {
    const status = this.shadowRoot?.querySelector(".status");
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("error", isError);
    status.hidden = !isError && !message && this._config.show_status === false;
  }

  _ean13Svg(raw, barHeight) {
    let digits = raw;
    if (digits.length === 12) digits += this._eanCheckDigit(digits);
    if (digits.length !== 13 || this._eanCheckDigit(digits.slice(0, 12)) !== digits[12]) {
      throw new Error("Unsupported EAN-13 value");
    }
    const left = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"];
    const right = ["1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100"];
    const parity = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"];
    const first = Number(digits[0]);
    let bits = "101";
    for (let i = 1; i <= 6; i++) {
      const pattern = left[Number(digits[i])];
      bits += parity[first][i - 1] === "G" ? pattern.split("").map((bit) => bit === "1" ? "0" : "1").join("") : pattern;
    }
    bits += "01010";
    for (let i = 7; i <= 12; i++) bits += right[Number(digits[i])];
    bits += "101";
    const bars = [];
    for (let i = 0; i < bits.length; i++) if (bits[i] === "1") bars.push(`<rect x="${11 + i}" y="0" width="1" height="${barHeight}"/>`);
    return `<svg viewBox="0 0 117 ${barHeight + 16}" role="img" aria-label="AB Plus barcode" xmlns="http://www.w3.org/2000/svg"><rect width="117" height="${barHeight + 16}" fill="#fff"/><g fill="#111" shape-rendering="crispEdges">${bars.join("")}</g><text x="58.5" y="${barHeight + 13}" text-anchor="middle" font-family="monospace" font-size="8" fill="#111">${digits}</text></svg>`;
  }

  _eanCheckDigit(twelveDigits) {
    const digits = String(twelveDigits);
    if (!/^\d{12}$/.test(digits)) throw new Error("Invalid EAN-13 value");
    let sum = 0;
    for (let i = 0; i < 12; i++) sum += Number(digits[i]) * (i % 2 === 0 ? 1 : 3);
    return String((10 - (sum % 10)) % 10);
  }
}

// Wait for Home Assistant's active custom-element registry. Its scoped-registry
// setup can replace window.customElements while frontend modules are loading.
let abPlusRegistrationAttempts = 0;
const registerABPlusCard = () => {
  const registry = window.customElements;
  if (!registry?.get("home-assistant")) {
    if (abPlusRegistrationAttempts++ < 200) {
      window.setTimeout(registerABPlusCard, 50);
    } else {
      console.error("AB Plus card could not find the active Home Assistant element registry.");
    }
    return;
  }
  if (!registry.get("ab-plus-card")) registry.define("ab-plus-card", ABPlusCard);
};
registerABPlusCard();
window.customCards = window.customCards || [];
const abPlusCardIsGreek = (document.documentElement.lang || "en").toLowerCase().startsWith("el");
if (!window.customCards.some((card) => card.type === "ab-plus-card")) {
  window.customCards.push({
    type: "ab-plus-card",
    name: abPlusCardIsGreek ? "Κάρτα AB Plus" : "AB Plus card",
    description: abPlusCardIsGreek
      ? "Εμφάνιση του barcode της κάρτας AB Plus."
      : "Display your AB Plus card barcode.",
  });
}
