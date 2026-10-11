/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewAction} ReviewAction */
/** @typedef {import("../../shared/api/reviewBatchContracts").AddedSemanticItem} AddedSemanticItem */
/** @typedef {import("../../shared/api/reviewBatchContracts").CoverageStatus} CoverageStatus */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewConflict} ReviewConflict */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewLabel} ReviewLabel */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewRecord} ReviewRecord */
/** @typedef {import("../../shared/api/reviewBatchContracts").SemanticItemReview} SemanticItemReview */
/** @typedef {import("./reviewAssessment").ReviewAssessment} ReviewAssessment */
/** @typedef {{record: ReviewRecord, labels: ReviewLabel[], onClose: () => void}} ReviewRecordDrawerProps */

/** @param {ReviewRecord} item @param {string} key @returns {string[]} */
export function values(item, key) {
  const source = item[key];
  return Array.isArray(source)
    ? source.filter((value) => typeof value === "string" && Boolean(value))
    : [];
}

/** @param {string[]} items @param {string} [empty] */
export function valueText(items, empty = "未提供") {
  return items.length ? items.join("、") : empty;
}
