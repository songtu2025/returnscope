export { taskLaunchCopy } from "./taskLaunchPolicy";

/** @type {readonly (readonly [string, "cheap_model" | "primary_model" | "secondary_model", "cheap_effort" | "primary_effort" | "secondary_effort", boolean])[]} */
export const MODEL_STAGES = [
  ["低成本初筛", "cheap_model", "cheap_effort", false],
  ["主分析", "primary_model", "primary_effort", true],
  ["风险复核", "secondary_model", "secondary_effort", false],
];

/** @param {import("./taskCreateContracts").AvailableModel[]} models
 * @param {TaskModelPolicy} policy
 */
export function taskModelPolicyError(models, policy) {
  const auditPercent = policy.cheap_audit_percent ?? 5;
  if (!Number.isInteger(auditPercent) || auditPercent < 0 || auditPercent > 100)
    return "初筛抽检比例应为 0 到 100 的整数";
  for (const [label, modelKey, effortKey, required] of MODEL_STAGES) {
    if (!policy[modelKey]) {
      if (required) return `请选择${label}模型`;
      continue;
    }
    const model = models.find((item) => item.model_key === policy[modelKey]);
    if (!model) return `${label}模型不可用，请重新选择`;
    if (!model.supported_efforts.includes(policy[effortKey]))
      return `${label}模型不支持当前推理强度，请重新选择`;
  }
  return "";
}

/** @typedef {import("./taskCreateContracts").ApiConnection} ApiConnection */
/** @typedef {import("./taskCreateContracts").DataVersion} DataVersion */
/** @typedef {import("./taskCreateContracts").PublishedConfig} PublishedConfig */
/** @typedef {import("./taskCreateContracts").ReturnImportResult} ReturnImportResult */
/** @typedef {import("./taskCreateContracts").TaskForm} TaskForm */
/** @typedef {import("./taskCreateContracts").TaskModelPolicy} TaskModelPolicy */
/** @typedef {import("./taskCreateContracts").TaskPlanViewState} TaskPlanViewState */
/** @typedef {import("./taskCreateContracts").TaskPreflightState} TaskPreflightState */
/** @typedef {import("../task-planning/taskPlanContracts").TaskExecutionPlan} TaskExecutionPlan */
/** @typedef {import("../task-planning/taskPlanContracts").TaskPlanCounts} TaskPlanCounts */

/** @param {ApiConnection[]} configs @param {string} configVersionId */
export function taskConnectionSelection(configs, configVersionId) {
  const publishedConfigs = configs.flatMap((item) =>
    item.active_version ? [{ ...item.active_version, connection_name: item.name }] : [],
  );
  const selectedConfig =
    publishedConfigs.find((item) => item.id === configVersionId) ?? publishedConfigs[0];
  const selectedConnection = configs.find(
    (item) => item.id === selectedConfig?.connection_id,
  );
  return { publishedConfigs, selectedConfig, selectedConnection };
}

/** @param {ApiConnection[]} configs @param {TaskForm} form @returns {TaskModelPolicy} */
export function resolveTaskModelPolicy(configs, form) {
  const { selectedConfig, selectedConnection } = taskConnectionSelection(
    configs,
    form.config_version_id,
  );
  return {
    connection_id: selectedConnection?.id ?? "",
    cheap_model: selectedConfig?.cheap_model ?? "",
    cheap_effort: selectedConfig?.cheap_effort ?? "low",
    primary_model: selectedConfig?.primary_model ?? "",
    primary_effort: selectedConfig?.primary_effort ?? "medium",
    secondary_model: selectedConfig?.secondary_model ?? "",
    secondary_effort: selectedConfig?.secondary_effort ?? "high",
    cheap_audit_percent: selectedConfig?.cheap_audit_percent ?? 5,
    ...form.model_policy,
  };
}

/** @param {PublishedConfig[]} publishedConfigs @param {string} configId @returns {TaskModelPolicy | null} */
export function taskConnectionPolicy(publishedConfigs, configId) {
  const config = publishedConfigs.find((item) => item.id === configId);
  if (!config) return null;
  return {
    connection_id: config.connection_id,
    cheap_model: config.cheap_model ?? "",
    cheap_effort: config.cheap_effort ?? "low",
    primary_model: config.primary_model,
    primary_effort: config.primary_effort ?? "medium",
    secondary_model: config.secondary_model ?? "",
    secondary_effort: config.secondary_effort ?? "high",
    cheap_audit_percent: config.cheap_audit_percent ?? 5,
  };
}

/** @param {DataVersion} item @returns {DataVersion} */
export function normalizeReturnVersion(item) {
  const stores = item.quality?.stores ?? [];
  return {
    ...item,
    dataset_name: item.source_name || returnSourceName(stores, item.dataset_name),
  };
}

/** @param {string[]} stores @param {string} fallback */
function returnSourceName(stores, fallback) {
  if (!stores.length) return fallback;
  const labels = stores.map((value) => value.replace(/[:_/\\-]+/g, " ").trim());
  return `${labels.join("、")} 用户反馈数据`;
}

/** @param {ReturnImportResult} result */
export function importSelectionLabel(result) {
  if (result.duplicate) return "已导入批次 · 直接复用";
  return "本次上传数据";
}

/** @param {ReturnImportResult} result */
export function importNotification(result) {
  if (result.duplicate) return "文件已导入过，已直接复用现有数据";
  return "用户反馈数据已导入并自动选中";
}

/** @param {TaskExecutionPlan | null | undefined} plan */
export function primaryPlanStore(plan) {
  return (
    plan?.primary_store ||
    plan?.inputs?.scope?.store ||
    plan?.detected_scopes?.find((scope) => scope.store)?.store ||
    ""
  );
}

/**
 * @param {TaskPreflightState & {counts: TaskPlanCounts}} preflight
 * @param {string} unresolvedPolicy
 * @param {boolean} scopeConfirmed
 * @returns {TaskPlanViewState}
 */
export function taskPlanViewState(preflight, unresolvedPolicy, scopeConfirmed) {
  const planCounts = preflight.counts;
  const blocked = (preflight.data?.blocked_count ?? 0) > 0;
  const categoryCompletionRequired = Boolean(
    preflight.data?.category_completion_required,
  );
  const countMismatch = Boolean(preflight.data && !planCounts.reconciled);
  const noExecutable = Boolean(preflight.data && planCounts.executable === 0);
  const partialPlan = planCounts.notAnalyzed > 0 && planCounts.executable > 0;
  const requiresScopeConfirmation = Boolean(
    partialPlan &&
    (preflight.data?.executable_count ?? 0) < planCounts.unique &&
    !categoryCompletionRequired &&
    (!blocked || unresolvedPolicy === "run_ready"),
  );
  const canContinue = Boolean(
    preflight.status === "ready" &&
    unresolvedPolicy &&
    !categoryCompletionRequired &&
    !countMismatch &&
    !noExecutable &&
    (!requiresScopeConfirmation || scopeConfirmed),
  );
  return {
    blocked,
    canContinue,
    categoryCompletionRequired,
    countMismatch,
    noExecutable,
    partialPlan,
    requiresScopeConfirmation,
  };
}

/**
 * @param {{dataEntryMode: "mysql" | "upload", mysqlDraft?: Partial<import("./mysqlReturnContracts").MysqlReturnFormState>, selectedReturns?: DataVersion, selectedDataLabel: string}} data
 */
export function taskDataScopeLabel({
  dataEntryMode,
  mysqlDraft,
  selectedReturns,
  selectedDataLabel,
}) {
  return dataEntryMode === "mysql"
    ? `${mysqlDraft?.store || mysqlDraft?.default_store || "全部店铺"} · ${mysqlDraft?.date_from || "不限开始日期"} — ${mysqlDraft?.date_to || "不限结束日期"}${mysqlDraft?.sku ? ` · 商品：${mysqlDraft.sku}` : ""}`
    : `上传文件 · ${selectedReturns?.dataset_name || selectedDataLabel}${selectedReturns?.version ? ` · 版本 ${selectedReturns.version}` : ""}`;
}
