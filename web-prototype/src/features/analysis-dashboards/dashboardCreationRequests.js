import { dashboardApi } from "../../shared/api/dashboardApi";

/** @typedef {import("./dashboardCreateContracts").DashboardCreateResponse} DashboardCreateResponse */
/** @typedef {import("./dashboardCreateContracts").DashboardSelection} DashboardSelection */

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
