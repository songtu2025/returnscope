import { Database, ListChecks, PlayCircle } from "@phosphor-icons/react";
import { STATUS_LABELS } from "../constants";

/** @typedef {import("./navigation").NavigationFocus} NavigationFocus */
/** @typedef {{id: string, title: string, owner_name: string, status: keyof typeof STATUS_LABELS, store: string, listing?: string}} SearchTask */
/** @typedef {{id: string, kind: string, name: string, current_version: number, row_count: number, description?: string}} SearchDataset */
/** @typedef {{id: string, workflow_status: string, comment: string, task_title: string, owner_name: string}} SearchReview */
/** @typedef {{tasks: SearchTask[], datasets: SearchDataset[], reviews: SearchReview[]}} SearchResources */
/** @typedef {{id: string, type: string, icon: import("react").ElementType, title: string, meta: string, keywords: string, page: string, focus: NavigationFocus}} GlobalSearchItem */

/** @param {SearchTask} task @returns {GlobalSearchItem} */
const taskSearchItem = (task) => ({
  id: task.id,
  type: "任务",
  icon: PlayCircle,
  title: task.title,
  meta: `${task.owner_name} · ${STATUS_LABELS[task.status] ?? task.status}`,
  keywords: `${task.title} ${task.store} ${task.listing ?? ""} ${task.owner_name}`,
  page: task.status === "completed" ? "legacy-results" : "analysis-tasks",
  focus: {
    kind: task.status === "completed" ? "result" : "task",
    id: task.id,
  },
});

/** @param {SearchDataset} dataset @returns {GlobalSearchItem} */
const datasetSearchItem = (dataset) => ({
  id: dataset.id,
  type: "产品信息",
  icon: Database,
  title: dataset.name,
  meta: `v${dataset.current_version} · ${dataset.row_count.toLocaleString()} 行`,
  keywords: `${dataset.name} ${dataset.description ?? ""} ${dataset.kind}`,
  page: "data-assets",
  focus: { kind: "dataset", id: dataset.id, datasetKind: dataset.kind },
});

/** @param {SearchReview} review @returns {GlobalSearchItem} */
const reviewSearchItem = (review) => ({
  id: review.id,
  type: review.workflow_status === "pending" ? "待复核" : "已复核",
  icon: ListChecks,
  title: review.comment,
  meta: `${review.task_title} · ${review.owner_name}`,
  keywords: `${review.comment} ${review.task_title} ${review.owner_name}`,
  page: "review",
  focus: { kind: "review", id: review.id, status: review.workflow_status },
});

/** @param {SearchResources} resources @param {string} query */
export function matchingSearchItems(resources, query) {
  const items = [
    ...resources.tasks.map(taskSearchItem),
    ...resources.datasets
      .filter((dataset) => dataset.kind === "products")
      .map(datasetSearchItem),
    ...resources.reviews.map(reviewSearchItem),
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
