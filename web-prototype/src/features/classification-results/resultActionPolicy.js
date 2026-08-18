const STATE_ALIASES = {
  ready: "ready",
  needs_review: "needs_review",
  review_required: "needs_review",
  "review-derived": "review-derived",
  review_derived: "review-derived",
  derived: "review-derived",
  unusable: "unusable",
};

export const RESULT_STATE_LABELS = {
  ready: "可用",
  needs_review: "需复核",
  "review-derived": "复核已发布",
  unusable: "不可用",
  unknown: "状态未提供",
};

const ACTIVE_REVIEW_STATUSES = new Set(["draft", "in_review", "conflict"]);

export function resultVersionId(result) {
  return result?.version_id || result?.result_version_id || result?.id || "";
}

export function resultState(result) {
  const explicit =
    result?.delivery_status ||
    result?.result_state ||
    result?.action_state ||
    result?.workflow_state ||
    "";
  if (STATE_ALIASES[explicit]) return STATE_ALIASES[explicit];

  if (
    result?.publish_origin === "review-derived" ||
    (result?.source_review_batch_id && result?.publish_status === "published")
  ) {
    return "review-derived";
  }

  const quality = result?.quality_status || result?.result_quality_status || "";
  return STATE_ALIASES[quality] || "unknown";
}

export function resultStateLabel(result) {
  return RESULT_STATE_LABELS[resultState(result)];
}

export function resultBlockingReason(result) {
  if (Array.isArray(result?.blocking_reasons)) {
    const messages = result.blocking_reasons
      .map((reason) => (typeof reason === "string" ? reason : reason?.message))
      .filter(Boolean);
    if (messages.length) return messages.join("；");
  }
  const supplied =
    result?.blocking_reason ||
    result?.action_blocking_reason ||
    result?.unusable_reason ||
    result?.quality_reason;
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

export function isDashboardSelectable(result) {
  const eligibleState = ["ready", "needs_review", "review-derived"].includes(
    resultState(result),
  );
  if (typeof result?.dashboard_eligibility === "boolean") {
    return eligibleState && result.dashboard_eligibility;
  }
  return eligibleState;
}

export function resultActionPolicy(result, options = {}) {
  const state = resultState(result);
  const dashboardSelectable = isDashboardSelectable(result);
  const activeBatch = options.activeBatch;
  const hasActiveBatch = activeBatch && ACTIVE_REVIEW_STATUSES.has(activeBatch.status);
  const derivedVersionId =
    options.derivedVersionId ||
    result?.derived_result_version_id ||
    result?.derived_version_id ||
    "";

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
    result?.source_task_id || result?.task_id || options.taskId || "";
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

export function activeReviewBatch(batches = []) {
  return batches.find((batch) => ACTIVE_REVIEW_STATUSES.has(batch.status)) || null;
}
