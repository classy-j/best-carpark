// App state.
//  PreferenceStore: the Driver's SearchPreference, kept in the browser (UC-08: no account needed).
//  SearchSession:   the last search request + response, so the Driver can go back to results,
//                   re-rank after changing preferences (UC-08 AF2) and sort/filter without searching
//                   again (UC-14). Kept in sessionStorage so a page refresh doesn't lose the results.

const FACTORS = ["PRICE", "WALKING_TIME", "AVAILABILITY"];
const LOT_TYPES = ["CAR", "MOTORCYCLE", "HEAVY_VEHICLE"];
const CARPARK_TYPES = ["MULTI_STOREY", "SURFACE", "BASEMENT", "COVERED", "SURFACE_MULTI_STOREY",
  "MECHANISED", "MECHANISED_AND_SURFACE"];

const DEFAULT_PREFERENCES = Object.freeze({
  priority_ranking: ["PRICE", "WALKING_TIME", "AVAILABILITY"],
  lot_type: "CAR",
  vehicle_height_m: null,
  carpark_types: [],
  ev_required: false,
});

function safeStorage(kind) {
  try { return window[kind]; } catch (_) { return null; }   // blocked storage throws on access
}

const PreferenceStore = (() => {
  const KEY = "bestCarpark.preferences.v1";
  let current = load();

  function clean(p) {
    const ranking = (Array.isArray(p.priority_ranking) ? p.priority_ranking : []).filter((f) => FACTORS.includes(f));
    FACTORS.forEach((f) => { if (!ranking.includes(f)) ranking.push(f); });   // keep all factors, once each
    const height = Number(p.vehicle_height_m);
    return {
      priority_ranking: [...new Set(ranking)],
      lot_type: LOT_TYPES.includes(p.lot_type) ? p.lot_type : DEFAULT_PREFERENCES.lot_type,
      vehicle_height_m: height > 0 && height <= 6 ? height : null,
      carpark_types: (Array.isArray(p.carpark_types) ? p.carpark_types : []).filter((t) => CARPARK_TYPES.includes(t)),
      ev_required: !!p.ev_required,
    };
  }

  function load() {
    try {
      const raw = safeStorage("localStorage")?.getItem(KEY);
      if (raw) return clean(JSON.parse(raw));
    } catch (_) { /* corrupt or blocked: fall back to defaults */ }
    return clean(DEFAULT_PREFERENCES);
  }

  return {
    get() { return structuredClone(current); },
    /** Saves and activates new preferences. Throws if they can't be stored (UC-08 EX1); the previous
     *  preferences then stay active. */
    save(prefs) {
      const next = clean(prefs);
      const storage = safeStorage("localStorage");
      if (!storage) throw new Error("Your browser is blocking local storage.");
      storage.setItem(KEY, JSON.stringify(next));
      current = next;
      return this.get();
    },
  };
})();

const SearchSession = (() => {
  const KEY = "bestCarpark.session.v1";
  let state = load();

  function load() {
    try {
      const raw = safeStorage("sessionStorage")?.getItem(KEY);
      if (raw) return JSON.parse(raw);
    } catch (_) { /* ignore */ }
    return { request: null, response: null, form: null, sort: "recommended", evOnly: false, view: "list" };
  }

  function persist() {
    try { safeStorage("sessionStorage")?.setItem(KEY, JSON.stringify(state)); } catch (_) { /* optional */ }
  }

  return {
    get request() { return state.request; },
    get response() { return state.response; },
    get form() { return state.form; },
    get sort() { return state.sort; },
    get evOnly() { return state.evOnly; },
    get view() { return state.view; },
    hasResults() { return !!(state.response && state.response.results && state.response.results.length); },
    setForm(form) { state.form = form; persist(); },
    setResults(request, response) {
      state.request = request;
      state.response = response;
      persist();
    },
    setSortFilter(sort, evOnly) { state.sort = sort; state.evOnly = evOnly; persist(); },
    setView(view) { state.view = view; persist(); },
    findResult(carparkId) {
      return state.response?.results?.find((r) => r.carpark.carpark_id === carparkId) || null;
    },
  };
})();
