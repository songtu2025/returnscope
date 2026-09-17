/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewBatch} ReviewBatch */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewBatchStatus} ReviewBatchStatus */

/** @type {Record<ReviewBatchStatus, string>} */
export const BATCH_STATUS_LABELS = {
  draft: "复核中",
  in_review: "复核中",
  conflict: "存在冲突",
  published: "已发布",
};

/** @param {ReviewBatch | null | undefined} batch */
export function pendingCount(batch) {
  return Number(batch?.pending_count ?? batch?.remaining_count ?? 0);
}
