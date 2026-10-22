// PreferenceUI «boundary»: Configure Ranking Preferences (UC-08).
// Two steps, as in the dialog map: RankFactors (order the factors) -> VehicleConfig (lot type,
// vehicle height, carpark types, EV). Edits a draft; nothing changes until Save.
class PreferenceUI {
  constructor({ onSave, onCancel }) {
    this.onSave = onSave;
    this.onCancel = onCancel;
    this.draft = null;
    this.step = "rank";

    $("#btn-prefs-save").addEventListener("click", () => this.btnSavePrefsClick());
    $("#btn-prefs-cancel").addEventListener("click", () => this.btnCancelPrefsClick());
    $("#btn-prefs-next").addEventListener("click", () => this.btnNextClick());
    $("#btn-prefs-back").addEventListener("click", () => this.btnBackClick());
    $("#vehicle-height").addEventListener("input", () => this.clearHeightError());
  }

  // ---- class diagram operations ----
  btnSavePrefsClick() {
    this.readVehicleConfig();
    const height = this.draft.vehicle_height_m;
    if (height != null && !(height >= 0.5 && height <= 6)) {
      this.goTo("vehicle");
      return this.showHeightError("Enter a height between 0.5 m and 6 m, or leave it empty.");
    }
    let saved;
    try {
      saved = PreferenceStore.save(this.draft);
    } catch (err) {                                          // UC-08 EX1: previous preferences stay active
      const el = $("#prefs-error");
      el.textContent = `Your preferences couldn't be saved (${err.message}). Your previous preferences are still in use.`;
      el.hidden = false;
      return;
    }
    this.onSave(saved);
  }

  btnCancelPrefsClick() {                                    // UC-08 AF1: nothing changes
    this.draft = null;
    this.onCancel();
  }

  btnNextClick() { this.goTo("vehicle"); }
  btnBackClick() { this.readVehicleConfig(); this.goTo("rank"); }

  // ---- screen ----
  show() {
    this.draft = PreferenceStore.get();                      // entry / load current preferences
    $("#prefs-error").hidden = true;
    this.clearHeightError();
    this.renderRankFactors();
    this.renderVehicleConfig();
    this.goTo("rank");
  }

  goTo(step) {
    this.step = step;
    $("[data-step=rank]").hidden = step !== "rank";
    $("[data-step=vehicle]").hidden = step !== "vehicle";
    $$("[data-step-label]").forEach((li) => li.classList.toggle("active", li.dataset.stepLabel === step));
    $("#btn-prefs-next").hidden = step !== "rank";
    $("#btn-prefs-back").hidden = step !== "vehicle";
    $("#btn-prefs-save").hidden = step !== "vehicle";
  }

  // RankFactors: ordered list with move up / move down buttons (keyboard and touch friendly).
  renderRankFactors(focusFactor, focusDir) {
    const list = $("#rank-list");
    const ranking = this.draft.priority_ranking;
    list.replaceChildren(...ranking.map((factor, i) => h("li", { class: "rank-item", dataset: { factor } },
      h("span", { class: "rank-pos" }, String(i + 1)),
      h("span", { class: "rank-name" }, Format.label(factor)),
      h("button", { type: "button", class: "icon-btn", "aria-label": `Move ${Format.label(factor)} up`,
        disabled: i === 0, dataset: { dir: "up" }, onclick: () => this.move(i, -1) }, "↑"),
      h("button", { type: "button", class: "icon-btn", "aria-label": `Move ${Format.label(factor)} down`,
        disabled: i === ranking.length - 1, dataset: { dir: "down" }, onclick: () => this.move(i, 1) }, "↓"),
    )));
    if (focusFactor) {
      const item = $(`[data-factor=${focusFactor}]`, list);
      const btn = $(`[data-dir=${focusDir}]:not([disabled])`, item) || $("button:not([disabled])", item);
      btn?.focus();
    }
  }

  move(index, delta) {
    const r = this.draft.priority_ranking;
    const target = index + delta;
    if (target < 0 || target >= r.length) return;
    [r[index], r[target]] = [r[target], r[index]];
    this.renderRankFactors(r[target], delta < 0 ? "up" : "down");
  }

  // VehicleConfig
  renderVehicleConfig() {
    const p = this.draft;
    $("#lot-type-group").replaceChildren(...LOT_TYPES.map((lot) => h("label", {},
      h("input", { type: "radio", name: "lotType", value: lot, checked: p.lot_type === lot }), " ", Format.label(lot))));
    $("#vehicle-height").value = p.vehicle_height_m ?? "";
    $("#carpark-type-group").replaceChildren(...CARPARK_TYPES.map((type) => h("label", { class: "chip" },
      h("input", { type: "checkbox", value: type, checked: p.carpark_types.includes(type) }), " ", Format.label(type))));
    $("#ev-required").checked = p.ev_required;
  }

  readVehicleConfig() {
    const heightRaw = $("#vehicle-height").value.trim();
    this.draft.lot_type = $("input[name=lotType]:checked")?.value || "CAR";
    this.draft.vehicle_height_m = heightRaw === "" ? null : Number(heightRaw);
    this.draft.carpark_types = $$("#carpark-type-group input:checked").map((c) => c.value);
    this.draft.ev_required = $("#ev-required").checked;
  }

  showHeightError(message) {
    const wrap = $("[data-field=vehicleHeight]");
    wrap.classList.add("invalid");
    $(".field-error", wrap).textContent = message;
    $("#vehicle-height").focus();
  }

  clearHeightError() {
    const wrap = $("[data-field=vehicleHeight]");
    wrap.classList.remove("invalid");
    $(".field-error", wrap).textContent = "";
  }
}
