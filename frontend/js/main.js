function buildPayload(form) {
  const f = new FormData(form);
  const height = parseFloat(f.get("vehicleHeight"));
  const duration = parseInt(f.get("duration"), 10);
  const payload = {
    destination_address: f.get("destination"),
    arrival_time: f.get("arrival"),                    // "YYYY-MM-DDTHH:mm" -> backend treats as Singapore time
    preference: {
      priority_ranking: [...new Set([f.get("p1"), f.get("p2"), f.get("p3")])],
      lot_type: f.get("lotType"),
      vehicle_height_m: Number.isNaN(height) || height <= 0 ? null : height,
      ev_required: f.get("ev") === "on",
    },
  };
  if (f.get("departure")) payload.departure_time = f.get("departure");
  else if (!Number.isNaN(duration)) payload.parking_duration_minutes = duration;
  return payload;
}

async function runSearch(payload, button) {
  button.disabled = true;
  setStatus("Searching…");
  try {
    const data = await searchCarparks(payload);
    renderResults(data.results);
    carparkMap.show(data.destination, data.results);
    setStatus(data.message || `${data.results.length} carparks found`);
  } catch (err) {
    if (err.status === 409 && err.body && err.body.matches) {      // pick one destination
      setStatus(err.message);
      renderChoices(err.body.matches, (m) =>
        runSearch({ ...payload, destination_address: m.name, destination_location: m.location }, button));
    } else {
      setStatus(err.message, true);
    }
  } finally {
    button.disabled = false;
  }
}

$("#search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  $("#choices").replaceChildren();
  runSearch(buildPayload(event.target), event.target.querySelector("button"));
});
