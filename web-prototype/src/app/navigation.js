import {
  BookOpenText,
  ChartLineUp,
  Database,
  GearSix,
  PlayCircle,
  SquaresFour,
  TreeStructure,
} from "@phosphor-icons/react";

/** @typedef {Record<string, string | undefined>} RouteQuery */
/** @typedef {{page: string, query: RouteQuery}} AppRoute */
/** @typedef {import("../features/task-create/taskCreateContracts").UnresolvedProduct} UnresolvedProduct */
/** @typedef {import("../features/task-create/taskCreateContracts").CategoryOption} CategoryOption */
/** @typedef {{kind: "task" | "task-template" | "return-version", id: string} | {kind: "result", id: string, listing?: string} | {kind: "classification-result", id: string, taskId?: string, segmentId?: string, listing?: string, reviewBatchId?: string} | {kind: "data-view", view: string} | {kind: "review", id: string, status?: string} | {kind: "review-batch", id: string, resultVersionId?: string} | {kind: "dataset", id?: string, datasetKind: string, returnToTask?: boolean, taskTitle?: string, store?: string, unresolvedProducts?: UnresolvedProduct[], categoryOptions?: CategoryOption[], blockedCommentCount?: number}} NavigationFocus */
/** @typedef {{route?: string, task_id?: string, segment_id?: string, result_version_id?: string, action?: string, dashboard_id?: string, version_id?: string, report_id?: string, batch_id?: string, review_id?: string, workflow_status?: string, dataset_id?: string, view?: string, tab?: string, connection_id?: string, config_version_id?: string, model_id?: string, entity_id?: string, user_id?: string}} NavigationTarget */
/** @typedef {{id: string, label: string, icon: import("react").ElementType}} NavigationItem */
/** @typedef {(destination: string, focus?: NavigationFocus | null) => void} Navigate */

/** @type {NavigationItem[]} */
export const PRIMARY_NAV_ITEMS = [
  { id: "workbench", label: "首页", icon: SquaresFour },
  { id: "data-assets", label: "数据资产", icon: Database },
  { id: "classification-standards", label: "分类标准", icon: BookOpenText },
  { id: "analysis-tasks", label: "分析任务", icon: PlayCircle },
  { id: "classification-results", label: "分类结果", icon: TreeStructure },
  { id: "analysis-dashboards", label: "分析看板", icon: ChartLineUp },
];

/** @type {NavigationItem} */
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
  "login",
  "forgot-password",
  "register",
  "reset-password",
  "change-email",
]);

/** @type {Record<string, {page: string, query?: RouteQuery}>} */
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

/**
 * @template {Record<string, string | undefined>} T
 * @param {RouteQuery} query
 * @param {T} source
 * @param {Array<[keyof T, string]>} fields
 */
function copyTruthyFields(query, source, fields) {
  for (const [sourceKey, queryKey] of fields) {
    if (source[sourceKey]) query[queryKey] = source[sourceKey];
  }
  return query;
}

/** @param {Extract<NavigationFocus, {kind: "dataset"}>} focus */
function datasetFocusQuery(focus) {
  const query = { dataset: focus.id, view: focus.datasetKind };
  if (focus.returnToTask) {
    return { ...query, return_to: "task-create", issue: "product-category" };
  }
  return query;
}

/** @param {NavigationFocus} focus @returns {RouteQuery} */
function focusQuery(focus) {
  switch (focus.kind) {
    case "task":
      return { task_id: focus.id };
    case "task-template":
      return { template_task: focus.id };
    case "result":
      return copyTruthyFields({ task_id: focus.id }, focus, [["listing", "listing"]]);
    case "classification-result":
      return copyTruthyFields({ result_version_id: focus.id }, focus, [
        ["taskId", "task_id"],
        ["segmentId", "segment_id"],
        ["listing", "listing"],
        ["reviewBatchId", "review_batch_id"],
      ]);
    case "return-version":
      return { dataset_version: focus.id };
    case "data-view":
      return { view: focus.view };
    case "review":
      return { review: focus.id, status: focus.status };
    case "review-batch":
      return copyTruthyFields({ review_batch_id: focus.id }, focus, [
        ["resultVersionId", "result_version_id"],
      ]);
    case "dataset":
      return datasetFocusQuery(focus);
  }
}

/** @type {Array<[keyof NavigationTarget, string]>} */
const TARGET_ENTITY_FIELDS = [
  ["task_id", "task_id"],
  ["segment_id", "segment_id"],
  ["result_version_id", "result_version_id"],
  ["action", "action"],
  ["dashboard_id", "dashboard"],
  ["version_id", "version"],
  ["report_id", "report"],
  ["batch_id", "review_batch_id"],
];
/** @type {Array<[keyof NavigationTarget, string]>} */
const TARGET_FILTER_FIELDS = [
  ["workflow_status", "status"],
  ["dataset_id", "dataset"],
  ["view", "view"],
  ["tab", "tab"],
  ["connection_id", "connection_id"],
  ["config_version_id", "config_version_id"],
  ["model_id", "model_id"],
  ["entity_id", "entity_id"],
  ["user_id", "user_id"],
];

/**
 * @param {string} destination
 * @param {NavigationFocus | null} [focus]
 * @returns {AppRoute}
 */
export function routeForDestination(destination, focus = null) {
  const legacy = LEGACY_ROUTES[destination];
  const page = legacy?.page ?? destination;
  const query = { ...(legacy?.query ?? {}) };
  if (focus) Object.assign(query, focusQuery(focus));
  return { page, query };
}

/**
 * @param {NavigationTarget | null | undefined} target
 * @returns {AppRoute | null}
 */
export function routeForTarget(target) {
  if (!target?.route) return null;
  const page = LEGACY_ROUTES[target.route]?.page ?? target.route;
  const query = { ...(LEGACY_ROUTES[target.route]?.query ?? {}) };
  copyTruthyFields(query, target, TARGET_ENTITY_FIELDS);
  if (target.review_id) {
    query[page === "review" ? "review" : "review_id"] = target.review_id;
  }
  copyTruthyFields(query, target, TARGET_FILTER_FIELDS);
  return { page, query };
}
