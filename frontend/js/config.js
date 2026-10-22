// Frontend settings. Change API_BASE_URL when the backend runs somewhere else.
// The backend only allows requests from http://localhost:5500 and http://127.0.0.1:5500 (CORS, see
// backend/app/config.py), so serve this folder on port 5500, e.g. with VS Code Live Server.
window.APP_CONFIG = {
  API_BASE_URL: "http://localhost:8000/api/v1",
  REQUEST_TIMEOUT_MS: 20000,
  TIME_ZONE: "Asia/Singapore",
  SEARCH_RADIUS_M: 1000,                     // FR1.4, drawn as a circle on the map
  MAP_CENTRE: [1.3521, 103.8198],
  LIMITED_HISTORY_SAMPLES: 6,                // fewer samples -> "based on limited data" (UC-05 AF1)
};
