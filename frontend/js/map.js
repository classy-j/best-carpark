// Leaflet map using OneMap's basemap tiles (FR6.2).
const carparkMap = (() => {
  const map = L.map("map").setView([1.3521, 103.8198], 12);
  L.tileLayer("https://www.onemap.gov.sg/maps/tiles/Default/{z}/{x}/{y}.png", {
    maxZoom: 19, minZoom: 11,
    attribution: 'Map data &copy; <a href="https://www.onemap.gov.sg/">OneMap</a> &amp; Singapore Land Authority',
  }).addTo(map);
  const layer = L.layerGroup().addTo(map);
  const markers = {};

  return {
    show(destination, items) {
      layer.clearLayers();
      Object.keys(markers).forEach(k => delete markers[k]);
      const points = [[destination.latitude, destination.longitude]];
      L.marker(points[0]).addTo(layer).bindPopup("Destination");
      items.forEach(it => {
        const p = [it.carpark.location.latitude, it.carpark.location.longitude];
        points.push(p);
        markers[it.carpark.carpark_id] = L.marker(p).addTo(layer).bindPopup(`${it.rank}. ${it.carpark.name}`);
      });
      map.fitBounds(points, { padding: [30, 30] });
    },
    focus(id) { markers[id]?.openPopup(); },
  };
})();
