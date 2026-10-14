import { request } from "./request";

/** @param {"model" | "standard"} kind @param {string} id @returns {Promise<{ok: boolean}>} */
export function cancelValidation(kind, id) {
  const path =
    kind === "model" ? "validation-runs" : "classification-standard-validation-runs";
  return request(`/api/${path}/${id}/cancel`, { method: "POST" });
}
