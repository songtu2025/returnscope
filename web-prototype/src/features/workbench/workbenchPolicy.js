import { navigateHash } from "../../app/hashRouter";
import { routeForTarget } from "../../app/navigation";

/** @typedef {import("../../shared/api/workbenchContracts").WorkbenchTarget} WorkbenchTarget */
/** @typedef {import("../../shared/api/workbenchContracts").WorkbenchAction} WorkbenchAction */
/** @typedef {{isLoading: boolean, hasData: boolean, message: string}} WorkbenchViewState */

/** @type {Record<string, string>} */
export const ACTION_LABELS = {
  blocked: "阻断",
  failed: "失败",
  review_required: "需复核",
  paused: "已暂停",
  report_running: "报告生成中",
  report_failed: "报告失败",
};

/** @type {Record<string, string>} */
export const OUTPUT_LABELS = {
  classification_result: "分类结果",
  derived_result: "复核派生结果",
  dashboard: "分析看板",
  insight_report: "AI 洞察报告",
};

/** @param {WorkbenchTarget} target */
export function openTarget(target) {
  const destination = routeForTarget(target);
  if (!destination) return;
  if (target?.action === "review" && destination.page === "classification-results") {
    navigateHash(destination.page, { ...destination.query, tab: "history" });
    return;
  }
  navigateHash(destination.page, destination.query);
}

/** @param {WorkbenchAction} action */
export function nextActionLabel(action) {
  if (action.type === "review_required") return "创建复核批次";
  if (action.type === "report_running") return "查看进度";
  if (action.type === "report_failed") return "查看并重试";
  return (
    (action.status ? ACTION_LABELS[action.status] : undefined) ??
    action.status ??
    "查看详情"
  );
}
