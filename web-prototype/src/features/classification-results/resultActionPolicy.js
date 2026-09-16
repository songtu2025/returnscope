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
 *
 * @typedef {{ id: string, status: string }} ReviewBatch
 * @typedef {{ activeBatch?: ReviewBatch | null, derivedVersionId?: string, taskId?: string }} ResultPolicyOptions
 * @typedef {
 *   | { kind: "create-dashboard", label: string, disabled?: boolean }
 *   | { kind: "enter-review", label: string, reviewBatchId: string, disabled?: boolean }
 *   | { kind: "create-review", label: string, disabled?: boolean }
 *   | { kind: "view-derived", label: string, resultVersionId: string, disabled?: boolean }
 *   | { kind: "repair-source", label: string, taskId: string, disabled?: boolean }
 *   | { kind: "view-blocker", label: string, disabled?: boolean }
 * } ResultPrimaryAction
 * @typedef {{ kind: "create-dashboard", label: string, disabled: boolean }} ResultSecondaryAction
 * @typedef {{
 *   state: ResultState,
 *   label: string,
 *   dashboardSelectable: boolean,
 *   primary: ResultPrimaryAction,
 *   secondary: ResultSecondaryAction | null,
 *   blockingReason: string
 * }} ResultPolicy
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
const RESULT_STATE_LABELS = {
  ready: "可用",
  needs_review: "需复核",
  "review-derived": "复核已发布",
  unusable: "不可用",
  unknown: "状态未提供",
};

const ACTIVE_REVIEW_STATUSES = new Set(["draft", "in_review", "conflict"]);

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
  const explicit =
    result?.delivery_status ||
    compatibilityString(result, "result_state") ||
    compatibilityString(result, "action_state") ||
    compatibilityString(result, "workflow_state");
  if (STATE_ALIASES[explicit]) return STATE_ALIASES[explicit];

  if (
    result?.publish_origin === "review-derived" ||
    (result?.source_review_batch_id && result?.publish_status === "published")
  ) {
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

/** @param {ResultPolicyInput | null | undefined} result @returns {string} */
function resultBlockingReason(result) {
  if (Array.isArray(result?.blocking_reasons)) {
    const messages = result.blocking_reasons
      .map((reason) => (typeof reason === "string" ? reason : reason?.message))
      .filter(Boolean);
    if (messages.length) return messages.join("；");
  }
  const supplied =
    compatibilityString(result, "blocking_reason") ||
    compatibilityString(result, "action_blocking_reason") ||
    compatibilityString(result, "unusable_reason") ||
    compatibilityString(result, "quality_reason");
  if (supplied) return supplied;

  const state = resultState(result);
  if (state === "needs_review") {
    return "当前版本仍有待复核数据；可先创建仅统计已可用数据的分析看板。";
  }
  if (state === "unusable") {
    return "当前版本不可用于复核或分析看板，请返回来源任务修复数据或重新分类。";
  }
  if (state === "unknown") {
    return "后端未返回可识别的结果质量状态，暂不能继续操作。";
  }
  return "";
}

/** @param {ResultPolicyInput | null | undefined} result @returns {boolean} */
export function isDashboardSelectable(result) {
  const eligibleState = ["ready", "needs_review", "review-derived"].includes(
    resultState(result),
  );
  if (typeof result?.dashboard_eligibility === "boolean") {
    return eligibleState && result.dashboard_eligibility;
  }
  return eligibleState;
}

/**
 * @param {ResultPolicyInput} result
 * @param {ResultPolicyOptions} [options]
 * @returns {ResultPolicy}
 */
export function resultActionPolicy(result, options = {}) {
  const state = resultState(result);
  const dashboardSelectable = isDashboardSelectable(result);
  const activeBatch = options.activeBatch;
  const hasActiveBatch = activeBatch && ACTIVE_REVIEW_STATUSES.has(activeBatch.status);
  const derivedVersionId =
    options.derivedVersionId ||
    compatibilityString(result, "derived_result_version_id") ||
    compatibilityString(result, "derived_version_id");

  if (state === "ready") {
    return {
      state,
      label: RESULT_STATE_LABELS[state],
      dashboardSelectable,
      primary: {
        kind: "create-dashboard",
        label: "创建分析看板",
        disabled: !dashboardSelectable,
      },
      secondary: null,
      blockingReason: dashboardSelectable ? "" : resultBlockingReason(result),
    };
  }

  if (state === "needs_review") {
    return {
      state,
      label: RESULT_STATE_LABELS[state],
      dashboardSelectable,
      primary: hasActiveBatch
        ? {
            kind: "enter-review",
            label: "进入复核批次",
            reviewBatchId: activeBatch.id,
          }
        : { kind: "create-review", label: "创建复核批次" },
      secondary: {
        kind: "create-dashboard",
        label: "创建已可用数据看板",
        disabled: !dashboardSelectable,
      },
      blockingReason: resultBlockingReason(result),
    };
  }

  if (state === "review-derived") {
    return {
      state,
      label: RESULT_STATE_LABELS[state],
      dashboardSelectable,
      primary: {
        kind: "view-derived",
        label: "查看衍生版本",
        resultVersionId: derivedVersionId || resultVersionId(result),
      },
      secondary: {
        kind: "create-dashboard",
        label: "创建分析看板",
        disabled: !dashboardSelectable,
      },
      blockingReason: dashboardSelectable ? "" : resultBlockingReason(result),
    };
  }

  const sourceTaskId =
    result?.source_task_id ||
    compatibilityString(result, "task_id") ||
    options.taskId ||
    "";
  return {
    state,
    label: RESULT_STATE_LABELS[state] || RESULT_STATE_LABELS.unknown,
    dashboardSelectable: false,
    primary: sourceTaskId
      ? {
          kind: "repair-source",
          label: "返回来源任务修复",
          taskId: sourceTaskId,
        }
      : { kind: "view-blocker", label: "查看阻断原因" },
    secondary: null,
    blockingReason: resultBlockingReason(result),
  };
}

/** @template {ReviewBatch} T @param {T[]} [batches] @returns {T | null} */
export function activeReviewBatch(batches = []) {
  return batches.find((batch) => ACTIVE_REVIEW_STATUSES.has(batch.status)) || null;
}
