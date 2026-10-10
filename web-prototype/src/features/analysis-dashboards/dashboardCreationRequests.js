import { dashboardApi } from "../../shared/api/dashboardApi";

/** @typedef {import("./dashboardCreateContracts").DashboardCreateResponse} DashboardCreateResponse */
/** @typedef {import("./dashboardCreateContracts").DashboardSelection} DashboardSelection */

/** @param {{selection:DashboardSelection,form:{name:string},common:{result_version_ids:string[],filters:DashboardSelection["filters"],plan_hash?:string,reason:string},isVersionCreation:boolean}} input */
export async function createDashboardFromPlan({
  selection,
  form,
  common,
  isVersionCreation,
}) {
  const targetDashboardId = selection.target_dashboard_id;
  /** @type {DashboardCreateResponse} */
  let created;
  if (isVersionCreation) {
    if (!targetDashboardId) {
      throw new Error("缺少目标看板，无法创建新版本");
    }
    created = await dashboardApi.createAnalysisDashboardVersion(targetDashboardId, {
      expected_revision: selection.expected_revision,
      ...common,
    });
  } else {
    created = await dashboardApi.createAnalysisDashboard({
      name: form.name.trim(),
      description: "",
      ...common,
    });
  }
  return created;
}
/** @param {DashboardCreateResponse} created @param {DashboardSelection} selection */
export function createdDashboardRoute(created, selection) {
  const dashboard = created.dashboard ?? created;
  const version = createdDashboardVersion(created);
  const dashboardId =
    dashboard.dashboard_id || dashboard.id || selection.target_dashboard_id;
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
