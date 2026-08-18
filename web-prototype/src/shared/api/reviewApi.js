import { request } from "./request";

export const reviewApi = {
  reviews: (status = "", options = {}) =>
    request(`/api/reviews${status ? `?workflow_status=${status}` : ""}`, options),
  review: (id, options = {}) => request(`/api/reviews/${id}`, options),
  resolveReview: (id, payload) =>
    request(`/api/reviews/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  taxonomy: () => request("/api/taxonomy"),
};
