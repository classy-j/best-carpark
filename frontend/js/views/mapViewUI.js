// MapViewUI «boundary»: destination and carparks as markers on a OneMap basemap (FR6.2, UC-14 AF1).
// Each carpark marker shows its current occupancy, like the bubbles in the Lab 1 mockup.

function createBaseMap(element, options = {}) {
  const map = L.map(element, { zoomControl: true, ...options }).setView(window.APP_CONFIG.MAP_CENTRE, 12);
  L.tileLayer("https://www.onemap.gov.sg/maps/tiles/Default/{z}/{x}/{y}.png", {
    maxZoom: 19, minZoom: 11, detectRetina: true,
    attribution: '<img src="https://www.onemap.gov.sg/web-assets/images/logo/om_logo.png" style="height:16px;width:16px;vertical-align:middle" alt=""> '
      + '<a href="https://www.onemap.gov.sg/" target="_blank" rel="noopener">OneMap</a> &copy; contributors &#124; '
      + '<a href="https://www.sla.gov.sg/" target="_blank" rel="noopener">Singapore Land Authority</a>',
  }).addTo(map);
  return map;
}

function destinationIcon() {
  return L.divIcon({ className: "pin-destination", html: "<span></span>", iconSize: [26, 26], iconAnchor: [13, 26] });
}

function carparkIcon(result, { selected = false } = {}) {
  const pct = Format.occupancyPct(result.availability);
  const level = Format.levelOf(pct);
  const stale = result.availability?.is_stale ? " stale" : "";
  const text = pct == null ? "?" : `${pct}%`;
  // text is a number we computed, so building the HTML string here is safe
  return L.divIcon({
    className: `pin-carpark level-${level}${stale}${selected ? " selected" : ""}`,
    html: `<span class="pin-rank">${Number.isFinite(Number(result.rank)) ? Number(result.rank) : "P"}</span><span class="pin-occ">${text}</span>`,
    iconSize: null, iconAnchor: [24, 30],
  });
}

class MapViewUI {
  constructor({ onSelect }) {
    this.onSelect = onSelect;
    this.map = null;
    this.layer = null;
    this.markers = new Map();
    this.pending = null;
  }

  ensureMap() {
    if (this.map) return;
    this.map = createBaseMap($("#map"));
    this.layer = L.layerGroup().addTo(this.map);
  }

  /** Called when the map tab becomes visible (Leaflet needs a visible container to size itself). */
  show() {
    this.ensureMap();
    this.map.invalidateSize();
    if (this.pending) { this.draw(...this.pending); this.pending = null; }
  }

  render(destination, results, visible) {
    if (!visible || !this.map) { this.pending = [destination, results]; return; }
    this.draw(destination, results);
  }

  draw(destination, results) {
    this.layer.clearLayers();
    this.markers.clear();
    const dest = [destination.latitude, destination.longitude];
    L.circle(dest, { radius: window.APP_CONFIG.SEARCH_RADIUS_M, className: "radius-circle", interactive: false })
      .addTo(this.layer);
    // Non-interactive so a carpark right next to the destination can still be clicked through it.
    L.marker(dest, { icon: destinationIcon(), title: "Destination", zIndexOffset: 1000000, interactive: false })
      .addTo(this.layer);

    const bounds = [dest];
    results.forEach((r) => {
      const pos = [r.carpark.location.latitude, r.carpark.location.longitude];
      bounds.push(pos);
      // Better-ranked carparks are drawn on top when markers overlap.
      const marker = L.marker(pos, { icon: carparkIcon(r), title: r.carpark.name, riseOnHover: true,
        zIndexOffset: (results.length - r.rank) * 1000 })
        .addTo(this.layer)
        .bindPopup(() => this.popup(r), { minWidth: 200 });
      this.markers.set(r.carpark.carpark_id, marker);
    });
    this.map.fitBounds(bounds, { padding: [40, 40], maxZoom: 17 });
  }

  popup(r) {
    return h("div", { class: "map-popup" },
      h("strong", {}, `${r.rank}. ${r.carpark.name}`),
      h("div", {}, `${Format.walkTime(r)} walk · est. ${Format.fee(r.estimated_fee_sgd)}`),
      h("div", {}, `Now: ${Format.lots(r.availability)}`, r.availability?.is_stale ? " (may be outdated)" : ""),
      h("button", { type: "button", class: "btn-primary small",
        onclick: () => this.onSelect(r.carpark.carpark_id) }, "View details"));
  }

  focus(carparkId) {
    const marker = this.markers.get(carparkId);
    if (!marker) return;
    this.map.setView(marker.getLatLng(), Math.max(this.map.getZoom(), 16));
    marker.openPopup();
  }
}
