import { navigateHash, parseHash } from "../../app/hashRouter";
import { RESULT_PAGE_SIZES } from "./classificationResultConstants";

/**
 * @typedef {Record<string, string | undefined> & { action?: "" | "review" }} ClassificationResultQuery
 */

/**
 * @typedef {object} ClassificationResultRoute
 * @property {string} version
 * @property {number} page
 * @property {number} recordPage
 * @property {number} pageSize
 * @property {string} q
 * @property {string} storeSite
 * @property {string} listing
 * @property {string} qualityStatus
 * @property {string} [lifecycle]
 * @property {string} recordQualityStatus
 * @property {string} commentStatus
 * @property {string} systemRerunRequired
 * @property {string} problem
 * @property {string} productName
 * @property {string} productSku
 * @property {string} orderId
 * @property {"results" | "reviews"} view
 * @property {"records" | "history"} tab
 * @property {string} selectionToken
 * @property {string} taskId
 * @property {string} [taskReturn]
 * @property {string} [dashboardReturn]
 * @property {string} segmentId
 * @property {string} reviewBatchId
 * @property {"" | "review"} action
 */

/**
 * @param {ClassificationResultQuery} query
 * @param {string} key
 */
function queryValue(query, key) {
  return query[key] || "";
}

/**
 * @param {ClassificationResultQuery} query
 * @returns {ClassificationResultRoute}
 */
export function classificationResultRouteState(query) {
  /** @param {string} key */
  const number = (key) => Number(query[key]);
  return {
    version: query.result_version_id || queryValue(query, "version"),
    page: Math.max(number("page") || 1, 1),
    recordPage: Math.max(number("record_page") || 1, 1),
    pageSize: RESULT_PAGE_SIZES.includes(number("page_size"))
      ? number("page_size")
      : 20,
    q: queryValue(query, "q"),
    storeSite: queryValue(query, "store_site"),
    listing: queryValue(query, "listing"),
    qualityStatus: queryValue(query, "quality_status"),
    lifecycle: queryValue(query, "lifecycle"),
    recordQualityStatus: queryValue(query, "record_quality_status"),
    commentStatus: queryValue(query, "comment_status"),
    systemRerunRequired: queryValue(query, "system_rerun_required"),
    problem: queryValue(query, "problem"),
    productName: queryValue(query, "product_name"),
    productSku: queryValue(query, "product_sku"),
    orderId: queryValue(query, "order_id"),
    view: query.view === "reviews" ? "reviews" : "results",
    tab: query.tab === "history" ? "history" : "records",
    selectionToken: queryValue(query, "selection_token"),
    taskId: queryValue(query, "task_id"),
    taskReturn: queryValue(query, "task_return"),
    dashboardReturn: queryValue(query, "dashboard_return"),
    segmentId: queryValue(query, "segment_id"),
    reviewBatchId: queryValue(query, "review_batch_id"),
    action: query.action || "",
  };
}

/** @param {ClassificationResultRoute} route */
export function classificationResultPoolQuery(route) {
  return {
    page: route.page > 1 ? route.page : "",
    page_size: route.pageSize !== 20 ? route.pageSize : "",
    q: route.q,
    store_site: route.storeSite,
    listing: route.listing,
    quality_status: route.qualityStatus,
    ...(route.lifecycle ? { lifecycle: route.lifecycle } : {}),
  };
}

/** @param {ClassificationResultRoute} route */
export function classificationResultPoolReturnQuery(route) {
  return {
    ...classificationResultPoolQuery(route),
    selection_token: route.selectionToken,
  };
}

/** @param {ClassificationResultRoute} route */
export function writeClassificationResultRoute(route) {
  navigateHash("classification-results", {
    ...classificationResultPoolReturnQuery(route),
    result_version_id: route.version,
    record_page: route.recordPage > 1 ? route.recordPage : "",
    record_quality_status: route.recordQualityStatus,
    comment_status: route.commentStatus,
    system_rerun_required: route.systemRerunRequired,
    problem: route.problem,
    product_name: route.productName,
    product_sku: route.productSku,
    order_id: route.orderId,
    tab: route.tab === "history" ? "history" : "",
    task_id: route.taskId,
    task_return: route.taskReturn,
    dashboard_return: route.dashboardReturn,
    segment_id: route.segmentId,
    review_batch_id: route.reviewBatchId,
    action: route.action,
  });
}

/** @param {ClassificationResultRoute} route @param {(changes: Partial<ClassificationResultRoute>) => void} updateRoute */
export function returnFromClassificationResult(route, updateRoute) {
  if (route.dashboardReturn) {
    const target = parseHash(route.dashboardReturn);
    if (target.page === "analysis-dashboards") {
      navigateHash(target.page, target.query);
      return;
    }
  }
  if (route.taskId) {
    const target = route.taskReturn ? parseHash(route.taskReturn) : null;
    navigateHash("analysis-tasks", {
      ...(target?.page === "analysis-tasks" ? target.query : {}),
      task_id: route.taskId,
      segment_id: route.segmentId,
    });
    return;
  }
  updateRoute({
    version: "",
    tab: "records",
    recordPage: 1,
    problem: "",
    productName: "",
    productSku: "",
    orderId: "",
    recordQualityStatus: "",
    commentStatus: "",
    systemRerunRequired: "",
  });
}

/** @param {ClassificationResultRoute} route */
export function classificationResultReturnLabel(route) {
  if (
    route.dashboardReturn &&
    parseHash(route.dashboardReturn).page === "analysis-dashboards"
  )
    return "返回分析看板";
  return route.taskId ? "返回任务" : "返回分类结果池";
}
