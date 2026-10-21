// All frontend <-> backend REST calls live here.
class ApiError extends Error {
  constructor(message, status, body) { super(message); this.status = status; this.body = body; }
}

async function searchCarparks(payload) {
  const res = await fetch(`${window.API_BASE_URL}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  let body = null;
  try { body = await res.json(); } catch (_) { /* empty body */ }
  if (!res.ok) {
    // FastAPI: string for our errors, array of {msg} for validation errors
    const d = body && body.detail;
    const msg = typeof d === "string" ? d : Array.isArray(d) ? d.map(x => x.msg).join("; ") : `Request failed (${res.status})`;
    throw new ApiError(msg, res.status, body);
  }
  return body;
}
