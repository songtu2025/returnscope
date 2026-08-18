import {
  ChartLineUp,
  Database,
  GearSix,
  PlayCircle,
  SquaresFour,
  TreeStructure,
} from "@phosphor-icons/react";

export const PRIMARY_NAV_ITEMS = [
  { id: "workbench", label: "首页", icon: SquaresFour },
  { id: "data-assets", label: "产品信息", icon: Database },
  { id: "analysis-tasks", label: "分析任务", icon: PlayCircle },
  { id: "classification-results", label: "分类结果", icon: TreeStructure },
  { id: "analysis-dashboards", label: "分析看板", icon: ChartLineUp },
];

export const SETTINGS_NAV_ITEM = {
  id: "settings",
  label: "系统设置",
  icon: GearSix,
};

export const PAGE_IDS = new Set([
  ...PRIMARY_NAV_ITEMS.map((item) => item.id),
  SETTINGS_NAV_ITEM.id,
  "task-create",
  "legacy-results",
  "review",
]);

export const LEGACY_ROUTES = {
  new: { page: "task-create" },
  tasks: { page: "analysis-tasks" },
  data: { page: "data-assets" },
  results: { page: "legacy-results" },
  "review-center": {
    page: "classification-results",
    query: { view: "reviews" },
  },
  api: { page: "settings", query: { tab: "api" } },
  team: { page: "settings", query: { tab: "users" } },
};

export function routeForDestination(destination, focus = null) {
  const legacy = LEGACY_ROUTES[destination];
  const page = legacy?.page ?? destination;
  const query = { ...(legacy?.query ?? {}) };

  if (!focus) return { page, query };
  if (focus.kind === "task") query.task_id = focus.id;
  if (focus.kind === "result") {
    query.task_id = focus.id;
    if (focus.listing) query.listing = focus.listing;
  }
  if (focus.kind === "classification-result") {
    query.result_version_id = focus.id;
    if (focus.taskId) query.task_id = focus.taskId;
    if (focus.segmentId) query.segment_id = focus.segmentId;
    if (focus.listing) query.listing = focus.listing;
    if (focus.reviewBatchId) query.review_batch_id = focus.reviewBatchId;
  }
  if (focus.kind === "return-version") query.dataset_version = focus.id;
  if (focus.kind === "data-view") query.view = focus.view;
  if (focus.kind === "review") {
    query.review = focus.id;
    query.status = focus.status;
  }
  if (focus.kind === "review-batch") {
    query.review_batch_id = focus.id;
    if (focus.resultVersionId) query.result_version_id = focus.resultVersionId;
  }
  if (focus.kind === "dataset") {
    query.dataset = focus.id;
    query.view = focus.datasetKind;
    if (focus.returnToTask) {
      query.return_to = "task-create";
      query.issue = "product-category";
    }
  }
  return { page, query };
}

export function routeForTarget(target) {
  if (!target?.route) return null;
  const page = LEGACY_ROUTES[target.route]?.page ?? target.route;
  const query = { ...(LEGACY_ROUTES[target.route]?.query ?? {}) };
  if (target.task_id) query.task_id = target.task_id;
  if (target.segment_id) query.segment_id = target.segment_id;
  if (target.result_version_id) query.result_version_id = target.result_version_id;
  if (target.action) query.action = target.action;
  if (target.dashboard_id) query.dashboard = target.dashboard_id;
  if (target.version_id) query.version = target.version_id;
  if (target.report_id) query.report = target.report_id;
  if (target.batch_id) query.review_batch_id = target.batch_id;
  if (target.review_id) {
    if (page === "review") query.review = target.review_id;
    else query.review_id = target.review_id;
  }
  if (target.workflow_status) query.status = target.workflow_status;
  if (target.dataset_id) query.dataset = target.dataset_id;
  if (target.view) query.view = target.view;
  if (target.tab) query.tab = target.tab;
  if (target.connection_id) query.connection_id = target.connection_id;
  if (target.config_version_id) query.config_version_id = target.config_version_id;
  if (target.model_id) query.model_id = target.model_id;
  if (target.entity_id) query.entity_id = target.entity_id;
  if (target.user_id) query.user_id = target.user_id;
  return { page, query };
}
