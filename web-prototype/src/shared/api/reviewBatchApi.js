import { queryString, request } from "./request";

/** @typedef {object} ReviewBatchPayload */
/** @typedef {Record<string, unknown>} ReviewBatchQuery */
/** @typedef {import("./reviewBatchContracts").ReviewBatch} ReviewBatch */
/** @typedef {import("./reviewBatchContracts").ReviewBatchPage} ReviewBatchPage */
/** @typedef {import("./reviewBatchContracts").ReviewRecord} ReviewRecord */
/** @typedef {import("./reviewBatchContracts").ReviewRecordPage} ReviewRecordPage */
/** @typedef {import("./reviewBatchContracts").PublishedReviewVersion} PublishedReviewVersion */
/** @typedef {import("./reviewBatchContracts").ReviewTaxonomy} ReviewTaxonomy */

/**
 * @type {{
 *   createReviewBatch: (versionId: string, payload: ReviewBatchPayload) => Promise<ReviewBatch>,
 *   reviewBatches: (filters?: ReviewBatchQuery, options?: RequestInit) => Promise<ReviewBatchPage>,
 *   reviewBatch: (batchId: string, options?: RequestInit) => Promise<ReviewBatch>,
 *   reviewBatchRecords: (batchId: string, filters?: ReviewBatchQuery, options?: RequestInit) => Promise<ReviewRecordPage>,
 *   updateReviewBatchRecord: (batchId: string, reviewId: string, payload: ReviewBatchPayload) => Promise<ReviewRecord>,
 *   updateReviewBatchRecords: (batchId: string, payload: ReviewBatchPayload) => Promise<unknown>,
 *   publishReviewBatch: (batchId: string, payload: ReviewBatchPayload) => Promise<PublishedReviewVersion>,
 *   reviewTaxonomy: (resultVersionId: string, options?: RequestInit) => Promise<ReviewTaxonomy>
 * }}
 */
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
  reviewTaxonomy: (resultVersionId, options = {}) =>
    request(
      resultVersionId
        ? `/api/classification-results/${resultVersionId}/taxonomy`
        : "/api/taxonomy",
      options,
    ),
};
