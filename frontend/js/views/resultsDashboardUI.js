// ResultsDashboardUI «boundary»: ranked results (UC-01 postconditions, FR6.1) with sort, filter and a
// list/map toggle (UC-14). Sorting and filtering re-use the last results; nothing is searched again.

// UC-14 AF2: a carpark with no value for the chosen factor goes to the end; ties keep the ranking.
const SORTERS = {
  recommended: () => 0,
  cheapest: by((r) => r.estimated_fee_sgd, "asc"),
  nearest: by((r) => r.walking_distance_m ?? r.straight_line_m, "asc"),
  available: by((r) => r.availability?.available_lots, "desc"),
};

/** Comparator on value(result); missing values always sort last, whatever the direction. */
function by(value, direction) {
  const sign = direction === "desc" ? -1 : 1;
  return (a, b) => {
    const x = value(a), y = value(b);
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return sign * (Number(x) - Number(y));
  };
}

/** Pure function so it can be unit tested: sort + filter a copy of the ranked results. */
function sortAndFilter(results, sort, evOnly) {
  const sorter = SORTERS[sort] || SORTERS.recommended;
  return results
    .filter((r) => !evOnly || r.ev_charging?.supported === true)        // FR4.6
    .slice()
    .sort((a, b) => sorter(a, b) || a.rank - b.rank);
}

class ResultsDashboardUI {
  constructor({ onEditSearch, onEditPrefs, onSelect }) {
    this.onEditSearch = onEditSearch;
    this.onEditPrefs = onEditPrefs;
    this.onSelect = onSelect;
    this.mapView = new MapViewUI({ onSelect: (id) => this.itemSelectClick(id) });

    $("#btn-edit-search").addEventListener("click", () => this.btnEditSearchClick());
    $("#btn-results-prefs").addEventListener("click", () => this.btnEditPrefsClick());
    $("#btn-list-toggle").addEventListener("click", () => this.btnListToggleClick());
    $("#btn-map-toggle").addEventListener("click", () => this.btnMapToggleClick());
    $("#sort-select").addEventListener("change", () => this.btnApplySortFilterClick());
    $("#ev-only").addEventListener("change", () => this.btnApplySortFilterClick());
  }

  // ---- class diagram operations ----
  btnApplySortFilterClick() {
    SearchSession.setSortFilter($("#sort-select").value, $("#ev-only").checked);
    this.renderResults();
  }

  btnListToggleClick() { this.setView("list"); }
  btnMapToggleClick() { this.setView("map"); }
  btnEditSearchClick() { this.onEditSearch(); }
  btnEditPrefsClick() { this.onEditPrefs(); }
  itemSelectClick(carparkId) { this.onSelect(carparkId); }

  // ---- screen ----
  /** entry / display ranked results */
  show() {
    const { request, response } = SearchSession;
    $("#sort-select").value = SearchSession.sort;
    $("#ev-only").checked = SearchSession.evOnly;
    this.renderHeader(request, response);
    this.renderResults();
    this.setView(SearchSession.view);
  }

  renderHeader(request, response) {
    $("#results-title").textContent = `Carparks near ${response.destination_address}`;
    const until = request.departure_time
      ? Format.time(request.departure_time)
      : `${Format.duration(request.parking_duration_minutes)} later`;
    $("#results-subtitle").textContent = [
      `${Format.dateTime(request.arrival_time)} – ${until}`,
      Format.label(request.preference.lot_type),
      `ranked by ${request.preference.priority_ranking.slice(0, 3).map((f) => Format.label(f).toLowerCase()).join(", ")}`,
    ].join(" · ");
  }

  renderResults() {
    const { request, response } = SearchSession;
    const all = response.results;
    const shown = sortAndFilter(all, SearchSession.sort, SearchSession.evOnly);
    const notice = $("#results-notice");

    if (!shown.length) {                                      // UC-14 EX1: offer to clear the filter
      notice.replaceChildren("No carparks in these results have known EV charging. ",
        h("button", { type: "button", class: "link", onclick: () => this.clearFilter() }, "Clear filter"));
      notice.hidden = false;
    } else {
      notice.textContent = shown.length === all.length
        ? `${all.length} carpark${all.length === 1 ? "" : "s"} within 1 km`
        : `Showing ${shown.length} of ${all.length} carparks`;
      notice.hidden = false;
    }

    $("#list-view").replaceChildren(...shown.map((r) => this.card(r, request)));
    this.mapView.render(response.destination, shown, SearchSession.view === "map");
  }

  clearFilter() {
    $("#ev-only").checked = false;
    this.btnApplySortFilterClick();
  }

  setView(view) {
    SearchSession.setView(view);
    const isMap = view === "map";
    $("#list-view").hidden = isMap;
    $("#map-view").hidden = !isMap;
    $("#btn-list-toggle").setAttribute("aria-pressed", String(!isMap));
    $("#btn-map-toggle").setAttribute("aria-pressed", String(isMap));
    if (isMap) this.mapView.show();
  }

  /** ListViewUI: one result card (FR6.1). */
  card(r, request) {
    const a = r.availability;
    const occ = Format.occupancyPct(a);
    const exp = r.expected_busyness;

    const badges = [
      r.ev_charging?.supported === true && h("span", { class: "badge badge-ev" }, "EV"),         // FR6.4
      a?.is_stale && h("span", { class: "badge badge-warn" }, "May be outdated"),                // FR6.3
      r.height_unknown && h("span", { class: "badge badge-warn" }, "Gantry height unknown"),     // FR4.4
    ];

    return h("button", { type: "button", class: "result-card", dataset: { id: r.carpark.carpark_id },
      onclick: () => this.itemSelectClick(r.carpark.carpark_id) },
      h("div", { class: "card-head" },
        h("span", { class: "rank" }, String(r.rank)),
        h("div", { class: "card-title" },
          h("h2", {}, r.carpark.name),
          h("span", { class: "muted" }, Format.label(r.carpark.carpark_type))),
        h("div", { class: "badges" }, badges)),
      h("dl", { class: "metrics" },
        metric("Walk", Format.walkTime(r), Format.walkDistance(r)),
        metric("Est. fee", Format.fee(r.estimated_fee_sgd), r.estimated_fee_sgd == null ? "no rate data" : "estimate"),
        metric("Now", Format.lots(a),
          a ? `${occ == null ? "" : `${occ}% full · `}updated ${Format.minutesAgo(a.last_updated)}` : "no live data",
          `level-${a?.is_stale ? "unknown" : Format.levelOf(occ)}`),
        metric(`Expected at ${Format.time(request.arrival_time)}`,
          exp ? Format.label(exp.level) : Format.UNAVAILABLE,
          exp ? `${exp.occupancy_pct}% full${Format.isLimitedHistory(exp) ? " · limited data" : ""}` : "not enough history",
          `expected level-${exp ? exp.level.toLowerCase() : "unknown"}`)));
  }
}

function metric(label, value, sub, cls) {
  return h("div", { class: `metric ${cls || ""}` },
    h("dt", {}, label),
    h("dd", {}, h("span", { class: "metric-value" }, value), sub && h("span", { class: "metric-sub" }, sub)));
}
