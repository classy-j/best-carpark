const $ = (sel) => document.querySelector(sel);

function setStatus(msg, isError = false) {
  const el = $("#status");
  el.textContent = msg;
  el.classList.toggle("error", isError);
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;          // textContent: data comes from external APIs
  return e;
}

function badge(text) { return el("span", "badge", text); }

function renderChoices(matches, onPick) {           // UC-01 AF1: several places match
  const list = $("#choices");
  list.replaceChildren();
  matches.forEach(m => {
    const li = el("li", null, m.address ? `${m.name} - ${m.address}` : m.name);
    li.addEventListener("click", () => { list.replaceChildren(); onPick(m); });
    list.append(li);
  });
}

function renderResults(items) {
  const list = $("#results");
  list.replaceChildren();
  items.forEach(it => {
    const li = el("li");
    const name = el("div", "name", `${it.rank}. ${it.carpark.name}`);
    const a = it.availability;
    if (a && a.is_stale) name.append(badge("may be outdated"));       // FR6.3
    if (it.height_unknown) name.append(badge("height unknown"));
    if (it.ev_charging.supported) name.append(badge("EV"));             // FR6.4

    const walk = it.walking_time_min == null
      ? `~${Math.round(it.straight_line_m)} m away (walking route unavailable)`
      : `${it.walking_time_min} min walk (${it.walking_distance_m} m)`;
    const fee = it.estimated_fee_sgd == null ? "fee unavailable" : `est. $${Number(it.estimated_fee_sgd).toFixed(2)}`;
    const now = a == null ? "availability unknown"
      : `${a.available_lots}${a.total_lots ? "/" + a.total_lots : ""} lots now`;
    const exp = it.expected_busyness == null ? "Expected: unavailable"
      : `Expected: ${it.expected_busyness.level} (${it.expected_busyness.occupancy_pct}% full)`;  // FR5.3 label

    li.append(name, el("div", "meta", `${walk} · ${fee}`), el("div", "meta", `${now} · ${exp}`));
    li.addEventListener("click", () => carparkMap.focus(it.carpark.carpark_id));
    list.append(li);
  });
}
