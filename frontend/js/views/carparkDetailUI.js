// CarparkDetailUI «boundary»: View Carpark Details (UC-09).
// Fee and walking time come from the search result (they depend on the search). Static info, current
// availability and expected busyness are fetched fresh from the backend; if a request fails, the
// value from the search result is used, and if there is nothing at all the field shows "Unavailable".
class CarparkDetailUI {
  constructor({ onClose }) {
    this.onClose = onClose;
    this.token = 0;
    this.miniMap = null;
    $("#btn-detail-close").addEventListener("click", () => this.btnCloseClick());
  }

  btnCloseClick() { this.onClose(); }

  async showDetails(carparkId) {
    const token = ++this.token;
    const body = $("#detail-body");
    body.replaceChildren(h("div", { class: "view-center" }, h("div", { class: "spinner" }), h("p", {}, "Loading carpark…")));

    const result = SearchSession.findResult(carparkId);
    const request = SearchSession.request;
    const lotType = request?.preference?.lot_type || PreferenceStore.get().lot_type;
    const arrival = request?.arrival_time || null;

    const [info, availability, busyness] = await Promise.allSettled([
      ApiClient.getCarpark(carparkId),
      ApiClient.getAvailability(carparkId, lotType),
      ApiClient.getExpectedBusyness(carparkId, lotType, arrival),
    ]);
    if (token !== this.token) return;                         // the Driver already moved on

    const carpark = info.status === "fulfilled" ? info.value : result?.carpark;
    if (!carpark) {                                            // UC-09 EX1
      const err = info.reason;
      body.replaceChildren(h("div", { class: "card error-card" },
        h("h1", {}, "Couldn't load this carpark"),
        h("p", {}, err?.code === "CARPARK_NOT_FOUND" ? "This carpark no longer exists in our data." : err?.message || ""),
        h("button", { type: "button", class: "btn-primary", onclick: () => this.btnCloseClick() }, "Back to results")));
      return;
    }

    const partialFailure = [info, availability, busyness].some((p) => p.status === "rejected");
    this.render({
      carpark,
      result,
      request,
      availability: availability.status === "fulfilled" ? availability.value : result?.availability ?? null,
      busyness: busyness.status === "fulfilled" ? busyness.value : result?.expected_busyness ?? null,
      partialFailure,
    });
  }

  render({ carpark, result, request, availability, busyness, partialFailure }) {
    const occ = Format.occupancyPct(availability);
    const loc = carpark.location;
    const ev = result?.ev_charging ?? { supported: carpark.has_ev_charging ?? null, available_chargers: null };
    const navigateUrl = `https://www.google.com/maps/dir/?api=1&destination=${loc.latitude},${loc.longitude}&travelmode=driving`;

    const body = $("#detail-body");
    body.replaceChildren(
      h("div", { class: "card detail-card" },
        h("div", { class: "detail-head" },
          result && h("span", { class: "rank" }, String(result.rank)),
          h("div", {},
            h("h1", {}, carpark.name),
            carpark.address && carpark.address !== carpark.name && h("p", { class: "muted" }, carpark.address))),

        partialFailure && h("p", { class: "notice warn" }, "Some details couldn't be refreshed, so the values from your search are shown."),
        availability?.is_stale && h("p", { class: "notice warn" },
          `Availability may be outdated: last updated ${Format.minutesAgo(availability.last_updated)}.`),   // UC-11

        h("div", { class: "detail-grid" },
          tile("Current occupancy", occ == null ? Format.UNAVAILABLE : `${occ}%`,
            availability ? `updated ${Format.minutesAgo(availability.last_updated)}` : "no live data",
            `level-${availability?.is_stale ? "unknown" : Format.levelOf(occ)}`),
          tile("Available lots", availability ? Format.lots(availability) : Format.UNAVAILABLE),
          tile(request ? `Expected at ${Format.time(request.arrival_time)}` : "Expected now",
            busyness ? `${busyness.occupancy_pct}% – ${Format.label(busyness.level)}` : Format.UNAVAILABLE,
            busyness ? `typical for this day and time${Format.isLimitedHistory(busyness) ? " (limited data)" : ""}`
              : "not enough history",
            `expected level-${busyness ? busyness.level.toLowerCase() : "unknown"}`),
          tile("Walking route", result ? Format.walkTime(result) : Format.UNAVAILABLE,
            result ? `${Format.walkDistance(result)} · ${result.walking_distance_m == null ? "Straight-line only; route unavailable" : "OneMap walking route"}` : null),
          tile("Estimated fee", result ? Format.fee(result.estimated_fee_sgd) : Format.UNAVAILABLE,
            result && result.estimated_fee_sgd != null ? "estimate for your parking period" : null),
          tile("EV charging", Format.ev(ev))),

        h("h2", {}, "Carpark information"),
        h("dl", { class: "info-list" },
          info("Carpark type", Format.label(carpark.carpark_type)),
          info("Parking system", Format.label(carpark.parking_system)),
          info("Gantry height", Format.metres(carpark.gantry_height_m)),
          info("Short-term parking", Format.label(carpark.short_term_parking)),
          info("Free parking", Format.label(carpark.free_parking)),
          info("Night parking", Format.yesNo(carpark.night_parking))),

        h("div", { id: "detail-map", class: "detail-map", "aria-label": "Map of carpark location" }),

        h("div", { class: "button-row" },
          h("a", { class: "btn-primary", href: navigateUrl, target: "_blank", rel: "noopener" }, "Navigate"),
          h("button", { type: "button", class: "btn-secondary", onclick: () => this.btnCloseClick() }, "Back to results"))));

    this.drawMiniMap(carpark, result);
  }

  drawMiniMap(carpark, result) {
    if (this.miniMap) { this.miniMap.remove(); this.miniMap = null; }
    const pos = [carpark.location.latitude, carpark.location.longitude];
    this.miniMap = createBaseMap($("#detail-map"), { scrollWheelZoom: false });
    const points = [pos];
    L.marker(pos, { icon: carparkIcon(result || { rank: "P", availability: null }) }).addTo(this.miniMap);
    const dest = SearchSession.response?.destination;
    if (result && dest) {
      const d = [dest.latitude, dest.longitude];
      L.marker(d, { icon: destinationIcon(), title: "Destination", interactive: false }).addTo(this.miniMap);
      points.push(d);
    }
    this.miniMap.fitBounds(points, { padding: [40, 40], maxZoom: 17 });
  }
}

function tile(label, value, sub, cls) {
  return h("div", { class: `tile ${cls || ""}` },
    h("span", { class: "tile-label" }, label),
    h("span", { class: "tile-value" }, value),
    sub && h("span", { class: "tile-sub" }, sub));
}

function info(label, value) {
  return h("div", {}, h("dt", {}, label), h("dd", {}, value));
}
