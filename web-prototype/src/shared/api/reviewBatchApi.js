import { queryString, request } from "./request";

/** @typedef {Record<string, unknown>} ReviewBatchQuery */
/** @typedef {import("./reviewBatchContracts").ReviewBatch} ReviewBatch */
/** @typedef {import("./reviewBatchContracts").ReviewBatchPage} ReviewBatchPage */
/** @typedef {import("./reviewBatchContracts").ReviewRecordPage} ReviewRecordPage */
/** @typedef {import("./reviewBatchContracts").ReviewTaxonomy} ReviewTaxonomy */

/**
 * @type {{
 *   reviewBatches: (filters?: ReviewBatchQuery, options?: RequestInit) => Promise<ReviewBatchPage>,
 *   reviewBatch: (batchId: string, options?: RequestInit) => Promise<ReviewBatch>,
 *   reviewBatchRecords: (batchId: string, filters?: ReviewBatchQuery, options?: RequestInit) => Promise<ReviewRecordPage>,
 *   reviewTaxonomy: (resultVersionId: string, options?: RequestInit) => Promise<ReviewTaxonomy>
 * }}
 */
export const reviewBatchApi = {
  reviewBatches: (filters = {}, options = {}) =>
    request(`/api/review-batches${queryString(filters)}`, options),
  reviewBatch: (batchId, options = {}) =>
    request(`/api/review-batches/${batchId}`, options),
  reviewBatchRecords: (batchId, filters = {}, options = {}) =>
    request(`/api/review-batches/${batchId}/records${queryString(filters)}`, options),
  reviewTaxonomy: (resultVersionId, options = {}) =>
    request(
      resultVersionId
        ? `/api/classification-results/${resultVersionId}/taxonomy`
        : "/api/taxonomy",
      options,
    ),
};
