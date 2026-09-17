import { request } from "./request";

/** @typedef {object} ReviewPayload */
/** @typedef {ReturnType<typeof request>} ReviewRequest */
/** @typedef {import("./reviewBatchContracts").LegacyReviewRecord} LegacyReviewRecord */

/**
 * @type {{
 *   reviews: (status?: string, options?: RequestInit) => Promise<LegacyReviewRecord[]>,
 *   review: (id: string, options?: RequestInit) => Promise<LegacyReviewRecord>,
 *   resolveReview: (id: string, payload: ReviewPayload) => Promise<LegacyReviewRecord>,
 *   taxonomy: () => ReviewRequest
 * }}
 */
export const reviewApi = {
  reviews: (status = "", options = {}) =>
    request(`/api/reviews${status ? `?workflow_status=${status}` : ""}`, options),
  review: (id, options = {}) => request(`/api/reviews/${id}`, options),
  resolveReview: (id, payload) =>
    request(`/api/reviews/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  taxonomy: () => request("/api/taxonomy"),
};
