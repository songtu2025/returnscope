import {
  compatibilityString,
  isDashboardSelectable,
  RESULT_STATE_LABELS,
  resultBlockingReason,
  resultState,
  resultVersionId,
} from "./resultStatePolicy";

export {
  isDashboardSelectable,
  resultState,
  resultStateLabel,
  resultVersionId,
} from "./resultStatePolicy";

/**
 * @typedef {import("./resultStatePolicy").ResultState} ResultState
 * @typedef {import("./resultStatePolicy").GeneratedResultVersion} GeneratedResultVersion
 * @typedef {import("./resultStatePolicy").GeneratedBlockingReason} GeneratedBlockingReason
 * @typedef {import("./resultStatePolicy").CompatibilityResultFields} CompatibilityResultFields
 * @typedef {import("./resultStatePolicy").CompatibilityResult} CompatibilityResult
 * @typedef {import("./resultStatePolicy").ResultPolicyInput} ResultPolicyInput
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

const ACTIVE_REVIEW_STATUSES = new Set(["draft", "in_review", "conflict"]);

/**
 * @param {ResultPolicyInput} result
 * @param {ResultState} state
 * @param {boolean} dashboardSelectable
 * @param {ReviewBatch | null | undefined} activeBatch
 * @returns {ResultPolicy}
 */
function reviewRequiredPolicy(result, state, dashboardSelectable, activeBatch) {
  return {
    state,
    label: RESULT_STATE_LABELS[state],
    dashboardSelectable,
    primary: activeBatch
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

/**
 * @param {ResultPolicyInput} result
 * @param {ResultState} state
 * @param {boolean} dashboardSelectable
 * @param {string} derivedVersionId
 * @returns {ResultPolicy}
 */
function reviewDerivedPolicy(result, state, dashboardSelectable, derivedVersionId) {
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

/**
 * @param {ResultPolicyInput} result
 * @param {ResultState} state
 * @param {ResultPolicyOptions} options
 * @returns {ResultPolicy}
 */
function blockedResultPolicy(result, state, options) {
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
    return reviewRequiredPolicy(
      result,
      state,
      dashboardSelectable,
      hasActiveBatch ? activeBatch : null,
    );
  }

  if (state === "review-derived") {
    return reviewDerivedPolicy(result, state, dashboardSelectable, derivedVersionId);
  }

  return blockedResultPolicy(result, state, options);
}

/** @template {ReviewBatch} T @param {T[]} [batches] @returns {T | null} */
export function activeReviewBatch(batches = []) {
  return batches.find((batch) => ACTIVE_REVIEW_STATUSES.has(batch.status)) || null;
}
