import { queryString, request } from "./request";

export const reviewBatchApi = {
  createReviewBatch: (versionId, payload) =>
    request(`/api/classification-results/${versionId}/review-batches`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  reviewBatches: (filters = {}, options = {}) =>
    request(`/api/review-batches${queryString(filters)}`, options),
  reviewBatch: (batchId, options = {}) =>
    request(`/api/review-batches/${batchId}`, options),
  reviewBatchRecords: (batchId, filters = {}, options = {}) =>
    request(`/api/review-batches/${batchId}/records${queryString(filters)}`, options),
  updateReviewBatchRecord: (batchId, reviewId, payload) =>
    request(`/api/review-batches/${batchId}/records/${reviewId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  updateReviewBatchRecords: (batchId, payload) =>
    request(`/api/review-batches/${batchId}/records`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  publishReviewBatch: (batchId, payload) =>
    request(`/api/review-batches/${batchId}/publish`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  reviewTaxonomy: (options = {}) => request("/api/taxonomy", options),
};
