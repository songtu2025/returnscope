/**
 * @typedef {"ready" | "needs_review" | "review-derived" | "unusable" | "unknown"} ResultState
 * @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultVersionResponse} GeneratedResultVersion
 * @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultBlockingReasonResponse} GeneratedBlockingReason
 * @typedef {object} CompatibilityResultFields
 * @property {string} [version_id]
 * @property {string} [result_version_id]
 * @property {string} [id]
 * @property {string} [delivery_status]
 * @property {string} [result_state]
 * @property {string} [action_state]
 * @property {string} [workflow_state]
 * @property {string} [publish_origin]
 * @property {string | null} [source_review_batch_id]
 * @property {string} [publish_status]
 * @property {string} [quality_status]
 * @property {string} [result_quality_status]
 * @property {boolean} [dashboard_eligibility]
 * @property {Array<string | GeneratedBlockingReason>} [blocking_reasons]
 * @property {string} [blocking_reason]
 * @property {string} [action_blocking_reason]
 * @property {string} [unusable_reason]
 * @property {string} [quality_reason]
 * @property {string} [derived_result_version_id]
 * @property {string} [derived_version_id]
 * @property {string} [source_task_id]
 * @property {string} [task_id]
 * @typedef {CompatibilityResultFields & Record<string, unknown>} CompatibilityResult
 * @typedef {GeneratedResultVersion | CompatibilityResult} ResultPolicyInput
 */

/** @type {Readonly<Record<string, ResultState>>} */
const STATE_ALIASES = {
  ready: "ready",
  needs_review: "needs_review",
  review_required: "needs_review",
  "review-derived": "review-derived",
  review_derived: "review-derived",
  derived: "review-derived",
  unusable: "unusable",
};

/** @type {Readonly<Record<ResultState, string>>} */
export const RESULT_STATE_LABELS = {
  ready: "可用",
  needs_review: "需复核",
  "review-derived": "复核已发布",
  unusable: "不可用",
  unknown: "状态未提供",
};

/**
 * @param {ResultPolicyInput | null | undefined} result
 * @param {string} key
 * @returns {string}
 */
function compatibilityString(result, key) {
  const value = result?.[key];
  return typeof value === "string" ? value : "";
}

/** @param {ResultPolicyInput | null | undefined} result @returns {string} */
export function resultVersionId(result) {
  return (
    result?.version_id ||
    compatibilityString(result, "result_version_id") ||
    compatibilityString(result, "id")
  );
}

/** @param {ResultPolicyInput | null | undefined} result @returns {ResultState} */
export function resultState(result) {
  const explicit = explicitResultState(result);
  if (STATE_ALIASES[explicit]) return STATE_ALIASES[explicit];

  if (isReviewDerivedResult(result)) {
    return "review-derived";
  }

  const quality =
    result?.quality_status || compatibilityString(result, "result_quality_status");
  return STATE_ALIASES[quality] || "unknown";
}

/** @param {ResultPolicyInput | null | undefined} result @returns {string} */
export function resultStateLabel(result) {
  return RESULT_STATE_LABELS[resultState(result)];
}

/** @param {ResultPolicyInput | null | undefined} result @returns {boolean} */
export function isDashboardSelectable(result) {
  return result?.publish_status === "published";
}

/** @param {ResultPolicyInput | null | undefined} result */
function explicitResultState(result) {
  return (
    result?.delivery_status ||
    compatibilityString(result, "result_state") ||
    compatibilityString(result, "action_state") ||
    compatibilityString(result, "workflow_state")
  );
}

/** @param {ResultPolicyInput | null | undefined} result */
function isReviewDerivedResult(result) {
  return Boolean(
    result?.publish_origin === "review-derived" ||
    (result?.source_review_batch_id && result?.publish_status === "published"),
  );
}
