import { navigateHash, parseHash } from "../../app/hashRouter";
import { PAGE_SIZES } from "../../shared/pagination";

/** @typedef {import("../../app/navigation").RouteQuery} RouteQuery */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewBatchRoute} ReviewBatchRoute */

/** @param {RouteQuery} query @returns {ReviewBatchRoute} */
export function reviewBatchRouteState(query) {
  /** @param {keyof RouteQuery} key */
  const number = (key) => Number(query[key]);
  return {
    batchId: query.review_batch_id || "",
    resultVersionId: query.result_version_id || "",
    status: query.status || "",
    page: Math.max(number("page") || 1, 1),
    pageSize: PAGE_SIZES.includes(number("page_size")) ? number("page_size") : 20,
    listing: query.listing || "",
    productName: query.product_name || "",
    productSku: query.product_sku || "",
    orderId: query.order_id || "",
    q: query.q || "",
    taskId: query.task_id || "",
    segmentId: query.segment_id || "",
    returnTo: query.return_to || "",
  };
}

/** @param {ReviewBatchRoute} route */
export function writeReviewBatchRoute(route) {
  navigateHash("classification-results", {
    view: "reviews",
    review_batch_id: route.batchId,
    result_version_id: route.resultVersionId,
    status: route.status,
    page: route.page > 1 ? route.page : "",
    page_size: route.pageSize !== 20 ? route.pageSize : "",
    listing: route.listing,
    product_name: route.productName,
    product_sku: route.productSku,
    order_id: route.orderId,
    q: route.q,
    task_id: route.taskId,
    segment_id: route.segmentId,
    return_to: route.returnTo,
  });
}

/** @param {ReviewBatchRoute} route @param {string} versionId @param {string} [tab] */
export function resultRouteQuery(route, versionId, tab = "") {
  const restored = route.returnTo ? parseHash(`#${route.returnTo}`).query : {};
  return {
    ...restored,
    result_version_id: versionId,
    review_batch_id: route.batchId,
    task_id: route.taskId || restored.task_id,
    segment_id: route.segmentId || restored.segment_id,
    tab,
    action: "",
  };
}
