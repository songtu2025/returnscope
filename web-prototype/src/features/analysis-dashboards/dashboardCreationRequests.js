import { dashboardApi } from "../../shared/api/dashboardApi";
import { parseHash } from "../../app/hashRouter";

/** @typedef {import("./dashboardCreateContracts").DashboardCreateResponse} DashboardCreateResponse */
/** @typedef {import("./dashboardCreateContracts").DashboardSelection} DashboardSelection */

/** @param {DashboardSelection | null} selection @param {string} token */
export function dashboardCreationReturn(selection, token) {
  const result = parseHash(selection?.result_return || "");
  if (result.page === "classification-results" && result.query.result_version_id)
    return { ...result, label: "返回分类结果详情" };
  const task = parseHash(selection?.task_return || "");
  if (task.page === "analysis-tasks" && task.query.task_id)
    return { ...task, label: "返回来源任务" };
  return {
    page: "classification-results",
    query: { ...selection?.result_pool_query, selection_token: token },
    label: "返回选择分类结果",
  };
}

/** @param {{form:{name:string},common:{result_version_ids:string[],filters:DashboardSelection["filters"],plan_hash?:string,reason:string}}} input */
export async function createDashboardFromPlan({ form, common }) {
  return dashboardApi.createAnalysisDashboard({
    name: form.name.trim(),
    description: "",
    ...common,
  });
}
/** @param {DashboardCreateResponse} created */
export function createdDashboardRoute(created) {
  const dashboard = created.dashboard ?? created;
  const version = createdDashboardVersion(created);
  const dashboardId = dashboard.dashboard_id || dashboard.id;
  const versionId =
    version.version_id || dashboard.current_version_id || created.version_id;
  if (!dashboardId || !versionId) {
    throw new Error("看板已生成，但服务端没有返回看板或版本标识");
  }
  return { dashboard: dashboardId, version: versionId, tab: "overview" };
}
/** @param {DashboardCreateResponse} created */
function createdDashboardVersion(created) {
  return created.version ?? created.current_version ?? created;
}
