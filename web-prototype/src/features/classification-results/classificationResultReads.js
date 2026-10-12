import { api } from "../../api";

/** @param {string} version @param {RequestInit} [options] */
export async function readResultOverview(version, options = {}) {
  const [result, summary] = await Promise.all([
    api.classificationResult(version, options),
    api.classificationResultSummary(version, options),
  ]);
  return { result, summary };
}

/** @param {import("./classificationResultRoute").ClassificationResultRoute} route */
export function resultRecordQuery(route) {
  return {
    page: route.recordPage,
    page_size: route.pageSize,
    problem: route.problem,
    product_name: route.productName,
    product_sku: route.productSku,
    order_id: route.orderId,
    quality_status: route.recordQualityStatus,
    comment_status: route.commentStatus,
    ...(route.systemRerunRequired
      ? { system_rerun_required: route.systemRerunRequired }
      : {}),
  };
}

/** @param {string} version @param {ReturnType<typeof resultRecordQuery>} query @param {RequestInit} [options] */
export async function readResultRecords(version, query, options = {}) {
  const [records, problems, names, skus] = await Promise.all([
    api.classificationResultRecordGroups(version, query, options),
    api.classificationResultDrilldown(
      version,
      "problem",
      { page: 1, page_size: 100 },
      options,
    ),
    api.classificationResultDrilldown(
      version,
      "product_name",
      { page: 1, page_size: 100, problem: query.problem },
      options,
    ),
    api.classificationResultDrilldown(
      version,
      "product_sku",
      {
        page: 1,
        page_size: 100,
        problem: query.problem,
        product_name: query.product_name,
      },
      options,
    ),
  ]);
  return {
    records,
    drilldowns: {
      problem: problems.items ?? [],
      product_name: names.items ?? [],
      product_sku: skus.items ?? [],
    },
  };
}
