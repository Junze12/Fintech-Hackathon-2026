// Same-origin calls to the copilot API. The session lives in an HttpOnly cookie the browser
// sends by itself; the page never sends a role or business. A 401 means "sign in again".

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

let onSignedOut = () => {};
export function whenSignedOut(fn) {
  onSignedOut = fn;
}

export async function api(path, { method = "GET", body, query } = {}) {
  let url = path;
  if (query) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) if (v !== null && v !== undefined && v !== "") qs.set(k, v);
    const text = qs.toString();
    if (text) url += `?${text}`;
  }
  const res = await fetch(url, {
    method,
    credentials: "same-origin",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (res.status === 401 && path !== "/api/session") onSignedOut();
  if (!res.ok) {
    const detail = data && data.detail;
    const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d) => d.msg).join("; ") : `Request failed (${res.status})`;
    throw new ApiError(res.status, message);
  }
  return data;
}

/** A gateway result {ok, message, data}: the data, or throw with the gateway's reason. */
export function unwrap(result) {
  if (!result || !result.ok) throw new ApiError(200, (result && result.message) || "Not available");
  return result.data;
}
