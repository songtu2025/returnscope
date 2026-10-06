export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
export const SESSION_EXPIRED_EVENT = "seekway:session-expired";

let sessionExpiredNotified = false;

export function resetSessionExpiration() {
  sessionExpiredNotified = false;
}

/** @param {Record<string, unknown>} [values] */
export function queryString(values = {}) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      params.set(key, String(value));
    }
  });
  const query = params.toString();
  return query ? `?${query}` : "";
}

export class ApiError extends Error {
  /**
   * @param {string} message
   * @param {number} status
   */
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

/** @param {Response} response */
function responsePayload(response) {
  const contentType = response.headers.get("content-type") ?? "";
  return contentType.includes("application/json") ? response.json() : response.text();
}

/** @param {unknown} item */
function validationMessage(item) {
  if (typeof item !== "object" || item === null || !("msg" in item)) return "";
  return item.msg == null ? "" : String(item.msg);
}

/** @param {unknown} payload */
function responseErrorMessage(payload) {
  const detail =
    typeof payload === "object" && payload !== null
      ? "detail" in payload
        ? payload.detail
        : undefined
      : payload;
  if (Array.isArray(detail)) return detail.map(validationMessage).join("；");
  return detail ? String(detail) : "请求失败";
}

/**
 * @param {string} path
 * @param {RequestInit} [options]
 */
export async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...options,
    headers: {
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...(options.headers ?? {}),
    },
  });
  if (response.status === 204) return null;
  const payload = await responsePayload(response);
  if (!response.ok) {
    if (
      response.status === 401 &&
      path !== "/api/auth/login" &&
      !sessionExpiredNotified
    ) {
      sessionExpiredNotified = true;
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
    throw new ApiError(responseErrorMessage(payload), response.status);
  }
  if (
    path === "/api/auth/login" ||
    path === "/api/auth/me" ||
    path === "/api/auth/register"
  ) {
    resetSessionExpiration();
  }
  return payload;
}
