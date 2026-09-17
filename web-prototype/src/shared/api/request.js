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
  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    if (
      response.status === 401 &&
      path !== "/api/auth/login" &&
      !sessionExpiredNotified
    ) {
      sessionExpiredNotified = true;
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
    const errorPayload = /** @type {unknown} */ (payload);
    const detail =
      typeof errorPayload === "object" && errorPayload !== null
        ? "detail" in errorPayload
          ? errorPayload.detail
          : undefined
        : errorPayload;
    const message = Array.isArray(detail)
      ? detail
          .map((item) =>
            typeof item === "object" && item !== null && "msg" in item
              ? item.msg == null
                ? ""
                : String(item.msg)
              : "",
          )
          .join("；")
      : detail
        ? String(detail)
        : "请求失败";
    throw new ApiError(message, response.status);
  }
  if (path === "/api/auth/login" || path === "/api/auth/me") {
    resetSessionExpiration();
  }
  return payload;
}
