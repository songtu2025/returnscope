export { taskLaunchCopy } from "./taskLaunchPolicy";

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

/** @param {ApiConnection[]} configs @param {TaskForm} form @returns {TaskModelPolicy} */
export function resolveTaskModelPolicy(configs, form) {
  const publishedConfigs = configs.flatMap((item) =>
    item.active_version ? [{ ...item.active_version, connection_name: item.name }] : [],
  );
  const selectedConfig =
    publishedConfigs.find((item) => item.id === form.config_version_id) ??
    publishedConfigs[0];
  const selectedConnection = configs.find(
    (item) => item.id === selectedConfig?.connection_id,
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

/** @param {DataVersion[]} items @returns {DataVersion[]} */
export function canonicalManagedReturns(items) {
  const grouped = new Map(/** @type {[string, DataVersion][]} */ ([]));
  items
    .filter(
      (item) =>
        item.usage_scope !== "task_input" && item.version === item.current_version,
    )
    .forEach((item) => {
      const stores = item.quality?.stores ?? [];
      const key = item.source_key || stores.slice().sort().join("|") || item.dataset_id;
      if (!grouped.has(key)) grouped.set(key, item);
    });
  return [...grouped.values()];
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
  if (result.mode === "append") return "合并后的当前完整数据";
  if (result.mode === "replace") return "替换后的当前完整数据";
  if (result.mode === "create") return "新建数据源 · 当前完整数据";
  return "本次上传数据";
}

/** @param {ReturnImportResult} result */
export function importNotification(result) {
  if (result.duplicate) return "文件已导入过，已直接复用现有数据";
  const imported = Number(result.summary?.imported_row_count ?? 0).toLocaleString();
  const skipped = Number(result.summary?.skipped_row_count ?? 0).toLocaleString();
  return result.mode === "append"
    ? `已追加 ${imported} 行，跳过 ${skipped} 行重复记录`
    : "用户反馈数据已导入并自动选中";
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
 * @param {{dataEntryMode: "mysql" | "upload" | "existing", mysqlDraft?: Partial<import("./mysqlReturnContracts").MysqlReturnFormState>, selectedReturns?: DataVersion, selectedDataLabel: string}} data
 */
export function taskDataScopeLabel({
  dataEntryMode,
  mysqlDraft,
  selectedReturns,
  selectedDataLabel,
}) {
  return dataEntryMode === "mysql"
    ? `${mysqlDraft?.store || mysqlDraft?.default_store || "全部店铺"} · ${mysqlDraft?.date_from || "不限开始日期"} — ${mysqlDraft?.date_to || "不限结束日期"}${mysqlDraft?.sku ? ` · 商品：${mysqlDraft.sku}` : ""}`
    : `${dataEntryMode === "upload" ? "上传文件" : "已有数据"} · ${selectedReturns?.dataset_name || selectedDataLabel}${selectedReturns?.version ? ` · 版本 ${selectedReturns.version}` : ""}`;
}
