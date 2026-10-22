// Display rules in one place, so every screen labels data the same way.
//  - Missing data (null) is shown as "Unavailable"/"Unknown", never as 0 (API spec: Missing Data, UC-01 AF3)
//  - Fees are always labelled as estimates (UC-03 special requirement)
//  - Historical estimates are always labelled "Expected" (FR5.3, NFR-U2)
//  - Availability older than 15 minutes is flagged "May be outdated" (FR6.3)
const Format = (() => {
  const tz = window.APP_CONFIG.TIME_ZONE;
  const UNAVAILABLE = "Unavailable";

  const LABELS = {
    PRICE: "Price", WALKING_TIME: "Walking time", AVAILABILITY: "Availability", EV_CHARGING: "EV charging",
    CAR: "Car", MOTORCYCLE: "Motorcycle", HEAVY_VEHICLE: "Heavy vehicle",
    MULTI_STOREY: "Multi-storey", SURFACE: "Surface", BASEMENT: "Basement", COVERED: "Covered",
    MECHANISED: "Mechanised", SURFACE_MULTI_STOREY: "Surface / multi-storey",
    MECHANISED_AND_SURFACE: "Mechanised and surface",
    ELECTRONIC: "Electronic", COUPON: "Coupon",
    LOW: "Low", MODERATE: "Moderate", HIGH: "High",
    WHOLE_DAY: "Whole day", "7AM_10_30PM": "7 am – 10.30 pm", "7AM_7PM": "7 am – 7 pm", NO: "No",
    SUN_PH_FR_7AM_10_30PM: "Sundays and public holidays, 7 am – 10.30 pm",
    SUN_PH_FR_1PM_10_30PM: "Sundays and public holidays, 1 pm – 10.30 pm",
  };

  // Unknown codes still read reasonably: "SOME_NEW_TYPE" -> "Some new type"
  function label(code) {
    if (code == null || code === "") return UNAVAILABLE;
    if (LABELS[code]) return LABELS[code];
    const text = String(code).replace(/_/g, " ").toLowerCase();
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  function fee(value) {
    if (value == null) return UNAVAILABLE;
    return `$${Number(value).toFixed(2)}`;
  }

  function walkTime(result) {
    const min = result.walking_time_min;
    if (min == null) return UNAVAILABLE;
    return min < 1 ? "< 1 min" : `${Math.round(min)} min`;
  }

  function distance(metres) {
    if (metres == null) return UNAVAILABLE;
    return metres >= 1000 ? `${(metres / 1000).toFixed(1)} km` : `${Math.round(metres)} m`;
  }

  // Walking distance if OneMap found a route, otherwise straight-line distance marked as such.
  function walkDistance(result) {
    if (result.walking_distance_m != null) return `${distance(result.walking_distance_m)} walk`;
    if (result.straight_line_m != null) return `${distance(result.straight_line_m)} away (straight line)`;
    return UNAVAILABLE;
  }

  function occupancyPct(availability) {
    if (!availability) return null;
    if (availability.occupancy_pct != null) return availability.occupancy_pct;
    const { available_lots: a, total_lots: t } = availability;
    return t ? Math.round(100 * (t - Math.min(a, t)) / t) : null;
  }

  function lots(availability) {
    if (!availability) return "Unknown";
    const a = availability.available_lots;
    return availability.total_lots ? `${a} / ${availability.total_lots} free` : `${a} free`;
  }

  // "LOW" / "MODERATE" / "HIGH" -> CSS class for colour; also used for live occupancy.
  function levelOf(pct) {
    if (pct == null) return "unknown";
    return pct > 90 ? "high" : pct > 70 ? "moderate" : "low";
  }

  function expected(busyness) {
    if (!busyness) return UNAVAILABLE;
    return `${label(busyness.level)} (${busyness.occupancy_pct}% full)`;
  }

  function isLimitedHistory(busyness) {
    return !!busyness && busyness.sample_count < window.APP_CONFIG.LIMITED_HISTORY_SAMPLES;
  }

  function ev(evCharging) {
    if (!evCharging || evCharging.supported == null) return "Unknown";
    if (!evCharging.supported) return "Not available";
    return evCharging.available_chargers == null
      ? "Available (chargers free: unavailable)"
      : `Available, ${evCharging.available_chargers} charger${evCharging.available_chargers === 1 ? "" : "s"} free`;
  }

  // Date/time strings from the backend carry +08:00; datetime-local values have no zone and mean SGT.
  function toDate(value) {
    if (value instanceof Date) return value;
    const hasZone = /([+-]\d\d:?\d\d|Z)$/.test(value);
    return new Date(hasZone ? value : `${value}+08:00`);
  }

  function dateTime(value) {
    return toDate(value).toLocaleString("en-SG", {
      timeZone: tz, weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit",
    });
  }

  function time(value) {
    return toDate(value).toLocaleTimeString("en-SG", { timeZone: tz, hour: "numeric", minute: "2-digit" });
  }

  function minutesAgo(value) {
    const mins = Math.round((Date.now() - toDate(value).getTime()) / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins} min ago`;
    const hours = Math.floor(mins / 60);
    return `${hours} h ${mins % 60} min ago`;
  }

  function duration(minutes) {
    const hrs = Math.floor(minutes / 60), mins = minutes % 60;
    return [hrs && `${hrs} h`, mins && `${mins} min`].filter(Boolean).join(" ") || "0 min";
  }

  function metres(value) {
    return value == null ? UNAVAILABLE : `${Number(value).toFixed(2)} m`;
  }

  function yesNo(value) {
    return value == null ? UNAVAILABLE : value ? "Yes" : "No";
  }

  return {
    UNAVAILABLE, label, fee, walkTime, walkDistance, distance, occupancyPct, lots, levelOf, expected,
    isLimitedHistory, ev, toDate, dateTime, time, minutesAgo, duration, metres, yesNo,
  };
})();
