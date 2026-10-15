/** @type {Record<string, string>} */
export const ACTION_LABELS = {
  create: "创建",
  update: "修改",
  validate: "验证",
  publish: "发布",
  delete: "删除",
  restore: "恢复",
  purge: "永久删除",
  remove: "移入回收站",
  remove_failed: "移除失败",
  archive: "归档任务",
  pause: "暂停任务",
  resume: "继续任务",
  retry: "重试任务",
  cancel: "取消",
  manual_correction: "人工修正语义",
  product_update: "更新产品信息",
  dimension_row_update: "修改产品信息",
  task_create: "创建任务",
  task_pause: "暂停任务",
  task_resume: "继续任务",
  task_cancel: "取消任务",
  segment_pause: "暂停 Listing",
  segment_resume: "继续 Listing",
  segment_cancel: "取消 Listing",
  segment_retry: "重试 Listing",
  segment_delete: "移除 Listing",
  segment_restore: "恢复 Listing",
  segment_remove_requested: "请求移除 Listing",
  reorder_segments: "调整 Listing 顺序",
  parallelism_changed: "调整任务并行数",
  retry_result_publish: "重试发布结果",
  semantic_restore: "恢复语义",
  review_update: "更新复核记录",
  review_batch_update: "更新复核批次",
  review_batch_publish: "发布复核版本",
  legacy_result_backfill_prepare: "准备回填历史结果",
  config_publish: "发布模型配置",
  user_update: "更新用户",
};
/** @type {Record<string, string>} */
export const ENTITY_LABELS = {
  task: "分析任务",
  task_segment: "Listing 片段",
  review: "历史复核记录",
  review_batch: "复核批次",
  dataset: "数据集",
  data_version: "数据版本",
  api_connection: "模型服务连接",
  api_model: "模型",
  api_config_version: "模型配置",
  config_version: "模型配置版本",
  model: "模型",
  user: "用户",
  classification_result: "分类结果",
  classification_result_version: "分类结果版本",
  analysis_dashboard: "分析看板",
  ai_insight_report: "AI 洞察报告",
  analysis_cleanup: "分析数据清理",
};
/** @param {import("../../shared/api/systemSettingsContracts").AuditLogEntry} item */
export function auditObjectLabel(item) {
  const snapshot = [item.after, item.before].find(
    (value) => typeof value === "object" && value !== null && "kind" in value,
  );
  const kind = item.target?.view ?? snapshot?.kind;
  if (item.entity_type === "dataset") {
    if (kind === "products") return "产品信息";
    if (kind === "returns") return "用户反馈数据";
  }
  return ENTITY_LABELS[item.entity_type ?? ""] ?? item.entity_type ?? "未提供对象";
}

/** @param {import("../../shared/api/systemSettingsContracts").AuditLogEntry} item */
export function auditObjectName(item) {
  for (const value of [item.after, item.before]) {
    if (!value || typeof value !== "object") continue;
    const entries = Object.entries(value);
    for (const field of ["display_name", "name", "model_key", "title"]) {
      const name = entries.find(([key]) => key === field)?.[1];
      if (typeof name === "string" && name) return name;
    }
  }
  return item.entity_id || "--";
}
