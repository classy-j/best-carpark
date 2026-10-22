// SearchEntryUI «boundary»: destination + arrival + departure time or duration (UC-01 steps 1-3).
// Validates input before anything is sent (UC-02) and highlights the invalid field (UC-02 EX2, UC-12).
class SearchEntryUI {
  static ARRIVAL_GRACE_MIN = 15;              // arrival may be up to 15 min in the past
  static MAX_DURATION_MIN = 7 * 24 * 60;      // same limit as the backend

  constructor({ onSearch, onEditPrefs }) {
    this.onSearch = onSearch;
    this.onEditPrefs = onEditPrefs;
    this.form = $("#search-form");

    this.form.addEventListener("submit", (e) => { e.preventDefault(); this.btnSearchClick(); });
    $("#btn-edit-prefs").addEventListener("click", () => this.btnEditPrefsClick());
    $$("input[name=periodMode]", this.form).forEach((r) => r.addEventListener("change", () => this.applyPeriodMode()));
    $$("input", this.form).forEach((input) => input.addEventListener("input", () => this.clearFieldError(input)));
    $("#arrival").addEventListener("change", () => this.keepDepartureAfterArrival());
    this.fill(SearchSession.form);
  }

  // ---- class diagram operations ----
  btnSearchClick() {
    this.clearErrors();
    const values = this.readForm();
    const errors = this.validate(values);
    if (Object.keys(errors).length) {
      Object.entries(errors).forEach(([field, msg]) => this.showFieldError(field, msg));
      this.focusFirstError();
      return;
    }
    SearchSession.setForm(values);
    this.onSearch(this.buildRequest(values));
  }

  btnEditPrefsClick() {
    SearchSession.setForm(this.readForm());   // keep what the Driver typed
    this.onEditPrefs();
  }

  // ---- screen ----
  show() {
    this.renderPrefsSummary();
    if (!$("#destination").value) $("#destination").focus();
  }

  fill(saved) {
    const arrival = defaultArrival();
    // Saved times that are already in the past are replaced by fresh defaults.
    const savedTimesOk = saved?.arrival && Format.toDate(saved.arrival).getTime() >= Date.now() - 60000;
    $("#destination").value = saved?.destination || "";
    $("#arrival").value = savedTimesOk ? saved.arrival : arrival;
    $("#departure").value = savedTimesOk && saved.departure > saved.arrival ? saved.departure : addMinutes($("#arrival").value, 120);
    $("#duration-hours").value = saved?.durationHours ?? 2;
    $("#duration-minutes").value = saved?.durationMinutes ?? 0;
    const mode = saved?.periodMode || "departure";
    $(`input[name=periodMode][value=${mode}]`, this.form).checked = true;
    this.applyPeriodMode();
  }

  applyPeriodMode() {
    const mode = this.periodMode();
    $("[data-field=departure]", this.form).hidden = mode !== "departure";
    $("[data-field=duration]", this.form).hidden = mode !== "duration";
  }

  keepDepartureAfterArrival() {
    const arrival = $("#arrival").value, departure = $("#departure").value;
    if (arrival && (!departure || departure <= arrival)) $("#departure").value = addMinutes(arrival, 120);
  }

  periodMode() {
    return $("input[name=periodMode]:checked", this.form).value;
  }

  readForm() {
    return {
      destination: $("#destination").value.trim(),
      arrival: $("#arrival").value,
      periodMode: this.periodMode(),
      departure: $("#departure").value,
      durationHours: $("#duration-hours").value,
      durationMinutes: $("#duration-minutes").value,
    };
  }

  /** Returns { fieldName: message } for every invalid field (UC-02 flow steps 1-4). */
  validate(v) {
    const errors = {};
    if (!v.destination) errors.destination = "Enter a destination.";

    const arrival = v.arrival ? Format.toDate(v.arrival) : null;
    if (!arrival || Number.isNaN(arrival.getTime())) {
      errors.arrival = "Enter your arrival date and time.";
    } else if (arrival.getTime() < Date.now() - SearchEntryUI.ARRIVAL_GRACE_MIN * 60000) {
      errors.arrival = "Arrival time can't be in the past.";
    }

    if (v.periodMode === "departure") {
      const departure = v.departure ? Format.toDate(v.departure) : null;
      if (!departure || Number.isNaN(departure.getTime())) errors.departure = "Enter your departure date and time.";
      else if (arrival && departure <= arrival) errors.departure = "Departure must be after arrival.";
      else if (arrival && departure - arrival > SearchEntryUI.MAX_DURATION_MIN * 60000) {
        errors.departure = "Parking period can't be longer than 7 days.";
      }
    } else {
      const total = durationMinutes(v);
      if (total == null) errors.duration = "Enter whole numbers of hours and minutes.";
      else if (total <= 0) errors.duration = "Duration must be more than 0 minutes.";
      else if (total > SearchEntryUI.MAX_DURATION_MIN) errors.duration = "Duration can't be longer than 7 days.";
    }
    return errors;
  }

  /** Form values -> backend SearchRequest (snake_case, see backend/app/schemas/search.py). */
  buildRequest(v) {
    const request = {
      destination_address: v.destination,
      arrival_time: v.arrival,                      // no zone: backend treats it as Singapore time
      preference: PreferenceStore.get(),
    };
    if (v.periodMode === "departure") request.departure_time = v.departure;
    else request.parking_duration_minutes = durationMinutes(v);
    return request;
  }

  renderPrefsSummary() {
    const p = PreferenceStore.get();
    const parts = [
      Format.label(p.lot_type),
      p.priority_ranking.slice(0, 3).map(Format.label).join(" › "),
      p.ev_required && "EV charging required",
      p.vehicle_height_m && `height ${p.vehicle_height_m} m`,
      p.carpark_types.length && `${p.carpark_types.length} carpark type${p.carpark_types.length > 1 ? "s" : ""}`,
    ].filter(Boolean);
    $("#prefs-summary-text").textContent = parts.join(" · ");
  }

  // ---- errors ----
  showFieldError(field, message) {
    const wrap = $(`[data-field=${field}]`, this.form);
    if (!wrap) return this.showFormError(message);
    wrap.classList.add("invalid");
    $(".field-error", wrap).textContent = message;
    $$("input", wrap).forEach((i) => i.setAttribute("aria-invalid", "true"));
  }

  showFormError(message) {
    const el = $("#search-error");
    el.textContent = message;
    el.hidden = false;
  }

  /** Called by the controller when the backend rejects the search. */
  showServerError(err) {
    if (err.code === "INVALID_DESTINATION") {            // UC-12 Invalid Destination Error
      this.showFieldError("destination",
        `We couldn't find "${$("#destination").value.trim()}". Check the spelling or try a nearby landmark.`);
    } else {
      this.showFormError(err.message);
    }
    this.focusFirstError();
  }

  clearFieldError(input) {
    const wrap = input.closest("[data-field]");
    if (!wrap) return;
    wrap.classList.remove("invalid");
    $(".field-error", wrap).textContent = "";
    input.removeAttribute("aria-invalid");
  }

  clearErrors() {
    $$("[data-field]", this.form).forEach((w) => {
      w.classList.remove("invalid");
      $(".field-error", w).textContent = "";
    });
    $$("[aria-invalid]", this.form).forEach((i) => i.removeAttribute("aria-invalid"));
    $("#search-error").hidden = true;
  }

  focusFirstError() {
    const first = $(".invalid input", this.form) || $("#search-error:not([hidden])");
    if (first && first.focus) first.focus();
  }
}

// ---- helpers (datetime-local values are "YYYY-MM-DDTHH:mm" in Singapore time) ----
function sgLocalString(date) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", {
    timeZone: window.APP_CONFIG.TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(date).map((p) => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

function defaultArrival() {                // now, rounded up to the next 15 minutes
  const step = 15 * 60000;
  return sgLocalString(new Date(Math.ceil(Date.now() / step) * step));
}

function addMinutes(localString, minutes) {
  return sgLocalString(new Date(Format.toDate(localString).getTime() + minutes * 60000));
}

function durationMinutes(v) {
  const hours = v.durationHours === "" ? 0 : Number(v.durationHours);
  const mins = v.durationMinutes === "" ? 0 : Number(v.durationMinutes);
  if (!Number.isInteger(hours) || !Number.isInteger(mins) || hours < 0 || mins < 0) return null;
  return hours * 60 + mins;
}
