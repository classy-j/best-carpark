// AppController: shows one screen at a time and moves between them as in the Lab 3 dialog map.
// Screens the Driver can come back to have a #route (so browser Back works):
//   #/search  #/preferences  #/results  #/carpark/<id>
// Loading, destination choice and "no results" are in-between states with no route of their own.
const App = (() => {
  let searchEntry, preferences, destinationChoice, dashboard, detail;
  let inFlight = null;                 // AbortController of the running search
  let prefsReturnRoute = "#/search";

  function showView(name) {
    $$("main > [data-view]").forEach((section) => { section.hidden = section.dataset.view !== name; });
    document.body.dataset.screen = name;
    window.scrollTo(0, 0);
  }

  function navigate(route) {
    if (location.hash === route) route_();      // same route: still re-render
    else location.hash = route;
  }

  // ---- routing ----
  function route_() {
    const hash = location.hash || "#/search";
    const carpark = hash.match(/^#\/carpark\/(.+)$/);
    if (hash === "#/preferences") {
      showView("preferences");
      preferences.show();
    } else if (hash === "#/results" && SearchSession.hasResults()) {
      showView("results");
      dashboard.show();
    } else if (carpark) {
      showView("detail");
      detail.showDetails(decodeURIComponent(carpark[1]));
    } else {
      if (hash !== "#/search") history.replaceState(null, "", "#/search");
      showView("search");
      searchEntry.show();
    }
  }

  // ---- search flow: SearchEntryUI -> LoadingUI -> results / choice / no results / error ----
  async function runSearch(request) {
    if (inFlight) inFlight.abort();
    inFlight = new AbortController();
    const controller = inFlight;

    $("#loading-text").textContent = `Finding carparks near ${request.destination_address}…`;
    showView("loading");

    let response;
    try {
      response = await ApiClient.searchCarparks(request, controller.signal);
    } catch (err) {
      if (controller !== inFlight) return;                       // superseded by a newer search
      inFlight = null;
      return handleSearchError(err, request);
    }
    if (controller !== inFlight) return;
    inFlight = null;

    SearchSession.setResults(request, response);
    if (!response.results.length) return showNoResults(response);   // UC-10 / UC-07 EX1
    navigate("#/results");
  }

  function handleSearchError(err, request) {
    if (err.code === "CANCELLED") return navigate("#/search");
    if (err.code === "MULTIPLE_DESTINATIONS") {                   // UC-01 AF1
      showView("choice");
      return destinationChoice.show(request.destination_address, err.body.matches);
    }
    navigate("#/search");                                         // dataLoadFailed / show error
    searchEntry.showServerError(err);
  }

  function showNoResults(response) {
    const unmet = /satisfy/i.test(response.message || "");
    $("#noresults-title").textContent = unmet ? "No carparks match your requirements" : "No carparks nearby";
    $("#noresults-text").textContent = response.message
      || "No supported carparks were found within 1 km of your destination.";
    $("#btn-noresults-prefs").hidden = !unmet;
    showView("noresults");
    $("#btn-modify-search").focus();
  }

  // ---- preferences flow ----
  function openPreferences() {
    const current = location.hash || "#/search";
    prefsReturnRoute = current === "#/preferences" ? "#/search" : current;
    if (document.body.dataset.screen === "noresults") prefsReturnRoute = "#/results";
    navigate("#/preferences");
  }

  function afterPreferencesSaved(prefs) {
    // UC-08 AF2: results already shown -> search again so the backend re-ranks with the new preferences
    if (prefsReturnRoute === "#/results" && SearchSession.request) {
      return runSearch({ ...SearchSession.request, preference: prefs });
    }
    navigate("#/search");
  }

  function afterPreferencesCancelled() {
    if (prefsReturnRoute === "#/results" && !SearchSession.hasResults() && SearchSession.response) {
      return showNoResults(SearchSession.response);
    }
    navigate(prefsReturnRoute);
  }

  function init() {
    searchEntry = new SearchEntryUI({ onSearch: runSearch, onEditPrefs: openPreferences });
    preferences = new PreferenceUI({ onSave: afterPreferencesSaved, onCancel: afterPreferencesCancelled });
    destinationChoice = new DestinationChoiceUI({
      onPick: (match) => runSearch({
        ...SearchSession.request,
        ...pendingRequestFromForm(),
        destination_address: match.name,
        destination_location: match.location,
      }),
      onBack: () => navigate("#/search"),
    });
    dashboard = new ResultsDashboardUI({
      onEditSearch: () => navigate("#/search"),
      onEditPrefs: openPreferences,
      onSelect: (id) => navigate(`#/carpark/${encodeURIComponent(id)}`),
    });
    detail = new CarparkDetailUI({
      onClose: () => navigate(SearchSession.hasResults() ? "#/results" : "#/search"),
    });

    $("#btn-header-prefs").addEventListener("click", openPreferences);
    $("#btn-loading-cancel").addEventListener("click", () => inFlight && inFlight.abort());
    $("#btn-modify-search").addEventListener("click", () => navigate("#/search"));
    $("#btn-noresults-prefs").addEventListener("click", () => { prefsReturnRoute = "#/results"; navigate("#/preferences"); });

    window.addEventListener("hashchange", route_);
    route_();
  }

  // The choice screen re-sends the search that produced it, built from the current form values.
  function pendingRequestFromForm() {
    const values = searchEntry.readForm();
    return searchEntry.buildRequest(values);
  }

  return { init };
})();

document.addEventListener("DOMContentLoaded", App.init);
