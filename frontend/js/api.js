// ApiClient: every frontend <-> backend REST call goes through here (REST + JSON).
// Backend errors come back in several shapes (FastAPI `detail` string, 422 validation array,
// 409 with `matches`), so they are turned into one ApiError with a code from the API spec.
class ApiError extends Error {
  /**
   * @param {string} code    INVALID_SEARCH_REQUEST | INVALID_DESTINATION | MULTIPLE_DESTINATIONS |
   *                         CARPARK_NOT_FOUND | EXTERNAL_SERVICE_UNAVAILABLE | NETWORK_ERROR |
   *                         TIMEOUT | INTERNAL_SERVER_ERROR
   */
  constructor(code, message, { status = null, body = null } = {}) {
    super(message);
    this.code = code;
    this.status = status;
    this.body = body;
  }
}

const ApiClient = (() => {
  const base = () => window.APP_CONFIG.API_BASE_URL;

  async function request(path, { method = "GET", body, signal, notFoundCode = "CARPARK_NOT_FOUND" } = {}) {
    const timeout = new AbortController();
    const timer = setTimeout(() => timeout.abort(), window.APP_CONFIG.REQUEST_TIMEOUT_MS);
    if (signal) signal.addEventListener("abort", () => timeout.abort(), { once: true });

    let res;
    try {
      res = await fetch(`${base()}${path}`, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
        signal: timeout.signal,
      });
    } catch (err) {
      if (signal && signal.aborted) throw new ApiError("CANCELLED", "Search cancelled.");
      if (timeout.signal.aborted) throw new ApiError("TIMEOUT", "The server took too long to respond. Please try again.");
      throw new ApiError("NETWORK_ERROR", "Can't reach the Best Carpark server. Check your connection and that the backend is running.");
    } finally {
      clearTimeout(timer);
    }

    let data = null;
    try { data = await res.json(); } catch (_) { /* empty or non-JSON body */ }
    if (res.ok) return data;
    throw toApiError(res.status, data, notFoundCode);
  }

  function toApiError(status, data, notFoundCode) {
    const detail = data && data.detail;
    const opts = { status, body: data };
    if (status === 409 && data && Array.isArray(data.matches)) {
      return new ApiError("MULTIPLE_DESTINATIONS", detail || "Several places match. Pick one.", opts);
    }
    if (status === 422) {
      const msg = Array.isArray(detail)
        ? detail.map((d) => String(d.msg || "").replace(/^Value error, /, "")).join(" ")
        : detail;
      return new ApiError("INVALID_SEARCH_REQUEST", msg || "Some search details are invalid.", opts);
    }
    if (status === 404) return new ApiError(notFoundCode, detail || "Not found.", opts);
    if (status === 502 || status === 503) {
      return new ApiError("EXTERNAL_SERVICE_UNAVAILABLE",
        "An external data service is temporarily unavailable. Please try again shortly.", opts);
    }
    return new ApiError("INTERNAL_SERVER_ERROR", "Something went wrong on the server. Please try again.", opts);
  }

  const enc = encodeURIComponent;

  return {
    /** POST /search -> { destination_address, destination, results[], message } */
    searchCarparks(searchRequest, signal) {
      return request("/search", { method: "POST", body: searchRequest, signal, notFoundCode: "INVALID_DESTINATION" });
    },
    /** GET /carparks/{id} -> static carpark information */
    getCarpark(carparkId) {
      return request(`/carparks/${enc(carparkId)}`);
    },
    /** GET /carparks/{id}/availability -> Availability or null */
    getAvailability(carparkId, lotType) {
      return request(`/carparks/${enc(carparkId)}/availability?lot_type=${enc(lotType)}`);
    },
    /** GET /carparks/{id}/expected-busyness -> ExpectedBusyness or null */
    getExpectedBusyness(carparkId, lotType, arrivalTime) {
      const at = arrivalTime ? `&at=${enc(arrivalTime)}` : "";
      return request(`/carparks/${enc(carparkId)}/expected-busyness?lot_type=${enc(lotType)}${at}`);
    },
  };
})();
