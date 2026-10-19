import { SEMANTIC_STATUS_LABELS } from "./semanticStatusPresentation";
import { RESULT_STATE_LABELS } from "./resultStatePolicy";

const EMPTY_CONDITIONS = {
  problem: "",
  productName: "",
  productSku: "",
  orderId: "",
  recordQualityStatus: "",
  commentStatus: "",
  systemRerunRequired: "",
};

/** @param {import("./classificationResultRoute").ClassificationResultRoute} route */
export function resultRecordConditions(route) {
  /** @type {Record<string, string>} */
  const qualityLabels = {
    ...RESULT_STATE_LABELS,
    review_required: RESULT_STATE_LABELS.needs_review,
    excluded: "已忽略",
  };
  return [
    ["问题", route.problem],
    ["产品名称", route.productName],
    ["产品SKU", route.productSku],
    ["订单号", route.orderId],
    [
      "结果状态",
      route.recordQualityStatus &&
        (qualityLabels[route.recordQualityStatus] || route.recordQualityStatus),
    ],
    [
      "语义类型",
      route.commentStatus &&
        (SEMANTIC_STATUS_LABELS[route.commentStatus] || route.commentStatus),
    ],
    [
      "重跑标记",
      route.systemRerunRequired &&
        (route.systemRerunRequired === "true" ? "需重跑" : "无需重跑"),
    ],
  ]
    .filter(([, value]) => Boolean(value))
    .map(([label, value]) => `${label}：${value}`);
}

/** @param {(changes: Partial<import("./classificationResultRoute").ClassificationResultRoute>) => void} updateRoute @param {Partial<import("./classificationResultRoute").ClassificationResultRoute>} [changes] */
export function clearResultRecordConditions(updateRoute, changes = {}) {
  updateRoute({ ...EMPTY_CONDITIONS, ...changes, recordPage: 1 });
}
