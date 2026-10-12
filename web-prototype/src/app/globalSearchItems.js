import { Database, ListChecks, PlayCircle } from "@phosphor-icons/react";
import { STATUS_LABELS } from "../constants";

/** @typedef {import("./navigation").NavigationFocus} NavigationFocus */
/** @typedef {{id: string, title: string, owner_name: string, status: keyof typeof STATUS_LABELS, store: string, listing?: string}} SearchTask */
/** @typedef {{id: string, kind: string, name: string, current_version: number, row_count: number, description?: string}} SearchDataset */
/** @typedef {import("../shared/api/generated/classification-results/types.gen").ClassificationResultGroupResponse} SearchFeedback */
/** @typedef {{tasks: SearchTask[], datasets: SearchDataset[], feedback: SearchFeedback[]}} SearchResources */
/** @typedef {{id: string, type: string, icon: import("react").ElementType, title: string, meta: string, keywords: string, page: string, focus: NavigationFocus}} GlobalSearchItem */

/** @param {SearchTask} task @returns {GlobalSearchItem} */
const taskSearchItem = (task) => ({
  id: task.id,
  type: "任务",
  icon: PlayCircle,
  title: task.title,
  meta: `${task.owner_name} · ${STATUS_LABELS[task.status] ?? task.status}`,
  keywords: `${task.title} ${task.store} ${task.listing ?? ""} ${task.owner_name}`,
  page: "analysis-tasks",
  focus: {
    kind: "task",
    id: task.id,
  },
});

/** @param {SearchDataset} dataset @returns {GlobalSearchItem} */
const datasetSearchItem = (dataset) => ({
  id: dataset.id,
  type: "商品信息",
  icon: Database,
  title: dataset.name,
  meta: `当前数据 · ${dataset.row_count.toLocaleString()} 行`,
  keywords: `${dataset.name} ${dataset.description ?? ""} ${dataset.kind}`,
  page: "data-assets",
  focus: { kind: "dataset", id: dataset.id, datasetKind: dataset.kind },
});

/** @param {SearchFeedback} group @returns {GlobalSearchItem} */
const feedbackSearchItem = ({ record }) => ({
  id: record.id,
  type: record.quality_status === "review_required" ? "待复核反馈" : "用户反馈",
  icon: ListChecks,
  title: record.comment || record.reason || record.order_id || "用户反馈",
  meta: `${record.listing} · ${record.order_id || "无订单号"}`,
  keywords: `${record.comment || ""} ${record.reason || ""} ${record.order_id || ""} ${record.listing || ""} ${record.product_name || ""}`,
  page: "classification-results",
  focus: {
    kind: "classification-result",
    id: record.result_version_id,
    listing: record.listing || undefined,
    orderId: record.order_id || undefined,
  },
});

/** @param {SearchResources} resources @param {string} query */
export function matchingSearchItems(resources, query) {
  const items = [
    ...resources.tasks.map(taskSearchItem),
    ...resources.datasets
      .filter((dataset) => dataset.kind === "products")
      .map(datasetSearchItem),
    ...resources.feedback.map(feedbackSearchItem),
  ];
  const normalized = query.trim().toLowerCase();
  const matches = items
    .filter(
      (item) =>
        !normalized ||
        `${item.title} ${item.keywords}`.toLowerCase().includes(normalized),
    )
    .slice(0, 12);

  return matches;
}
