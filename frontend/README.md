# Frontend (Person E)

Plain HTML/CSS/JavaScript + [Leaflet](https://leafletjs.com/) with OneMap basemap tiles. No build step.

## Run

1. Start the backend (see `backend/README.md`): `uvicorn app.main:app --reload` → http://localhost:8000
2. Serve this folder on **port 5500** (the backend only accepts CORS requests from `localhost:5500` /
   `127.0.0.1:5500`): VS Code → right-click `index.html` → **Open with Live Server**, or
   `python -m http.server 5500` from this folder.
3. Open http://localhost:5500/index.html

The backend URL is set in `js/config.js` (`API_BASE_URL`).

## Structure — one boundary class per file (Lab 3 class diagram / dialog map)

| File | Class | Dialog-map state / use case |
|---|---|---|
| `js/views/searchEntryUI.js` | `SearchEntryUI` — `btnSearchClick()`, `btnEditPrefsClick()` | SearchEntryUI (UC-01, UC-02, UC-12) |
| `js/views/preferenceUI.js` | `PreferenceUI` — `btnSavePrefsClick()`, `btnCancelPrefsClick()` | PreferenceUI → RankFactors / VehicleConfig (UC-08) |
| `js/views/destinationChoiceUI.js` | `DestinationChoiceUI` — `itemSelectClick()` | DestinationChoiceUI (UC-01 AF1) |
| `js/views/resultsDashboardUI.js` | `ResultsDashboardUI` — `btnApplySortFilterClick()`, `btnListToggleClick()`, `btnMapToggleClick()`, `btnEditSearchClick()`, `btnEditPrefsClick()`, `itemSelectClick(carparkId)` | ResultsDashboardUI → ListViewUI (UC-14) |
| `js/views/mapViewUI.js` | `MapViewUI` | MapViewUI (FR6.2, UC-14 AF1) |
| `js/views/carparkDetailUI.js` | `CarparkDetailUI` — `showDetails(carparkId)`, `btnCloseClick()` | CarparkDetailUI (UC-09) |
| `js/app.js` | `App` controller | Switches screens; LoadingUI and NoResultsUI (UC-10) |
| `js/api.js` | `ApiClient` | All REST calls; maps HTTP errors to the API spec error codes |
| `js/state.js` | `PreferenceStore`, `SearchSession` | Preferences kept in the browser (UC-08); last search for sort/filter/back |
| `js/format.js` | `Format` | Display rules: "Unavailable", "est.", "Expected", "May be outdated" |
| `js/dom.js` | `h()` helper | Builds DOM with `textContent` only (external data is never injected as HTML) |

Routes: `#/search`, `#/preferences`, `#/results`, `#/carpark/<id>` — the browser Back button works.

## Backend endpoints used

All under `/api/v1` (snake_case JSON, see `backend/app/schemas/`):

| Call | Used by |
|---|---|
| `POST /search` | SearchEntryUI, PreferenceUI re-rank (UC-08 AF2), DestinationChoiceUI (`destination_location`) |
| `GET /carparks/{id}` | CarparkDetailUI (static info) |
| `GET /carparks/{id}/availability?lot_type=` | CarparkDetailUI (fresh live availability) |
| `GET /carparks/{id}/expected-busyness?lot_type=&at=` | CarparkDetailUI (expected at arrival time) |

| HTTP status | Shown as |
|---|---|
| 404 on search | Destination field highlighted (UC-12) |
| 409 | List of matching places (UC-01 AF1) |
| 422 | Validation message from the backend |
| 502 / 503 | "External data service temporarily unavailable" |
| network error / timeout | "Can't reach the Best Carpark server" |
| 200 with empty `results` | NoResultsUI with the backend's `message` (UC-10, UC-07 EX1) |

## Requirement checklist

- FR1.1/1.3 destination, arrival, departure **or** duration · FR1.5 / UC-10 no-carparks message
- FR4.1 rank factors · FR4.3 lot type · FR4.4 vehicle height (unknown gantry flagged) · FR4.5 sort · FR4.6 EV filter
- FR5.3 / NFR-U2 expected busyness labelled "Expected" and styled differently from live data
- FR6.1 result cards · FR6.2 map markers · FR6.3 "May be outdated" (> 15 min) · FR6.4 EV badge
- NFR-U1 works on mobile and desktop (single-column layout below 760 px)
