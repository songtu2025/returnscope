/** @typedef {import("./dashboardCreateContracts").DashboardSelectionItem} DashboardSelectionItem */
/** @typedef {import("./dashboardCreateContracts").DashboardSelection} DashboardSelection */
/** @typedef {import("./dashboardCreateContracts").DashboardConflict} DashboardConflict */
/** @typedef {import("./dashboardCreateContracts").DashboardPlan} DashboardPlan */

/** @param {DashboardSelectionItem} item */
export function itemVersionId(item) {
  return item.result_version_id || item.version_id || item.id || "";
}

/**
 * @param {DashboardConflict} conflict
 * @param {number} index
 */
export function conflictId(conflict, index) {
  return (
    conflict.conflict_id ||
    conflict.key ||
    `${conflict.store_site}:${conflict.listing}:${index}`
  );
}

/**
 * @param {DashboardConflict} conflict
 * @param {DashboardSelection | null} selection
 * @param {DashboardSelectionItem[]} [sources]
 */
export function conflictCandidates(conflict, selection, sources = []) {
  const ids = new Set(conflict.result_version_ids ?? []);
  const planned = sources.filter((item) => ids.has(item.result_version_id));
  return planned.length
    ? planned
    : (selection?.selected ?? []).filter((item) => ids.has(item.result_version_id));
}

/**
 * @param {DashboardSelection | null} selection
 * @param {string[]} ids
 */
function selectedForIds(selection, ids) {
  const allowed = new Set(ids);
  return (selection?.selected ?? []).filter((item) =>
    allowed.has(item.result_version_id),
  );
}

/** @param {import("./dashboardCreateContracts").DashboardPlan | null} value @param {DashboardSelection | null} selection @param {string[]} resultVersionIds */
export function dashboardCreationPlan(value, selection, resultVersionIds) {
  /** @type {Partial<import("./dashboardCreateContracts").DashboardPlan>} */ const plan =
    value ?? {};
  return {
    conflicts: plan.conflicts ?? [],
    blockers: plan.blockers ?? [],
    warnings: plan.warnings ?? [],
    currentSources: plannedSources(value, selection, resultVersionIds),
    summary: plan.summary ?? {},
    isVersionCreation: Boolean(selection?.target_dashboard_id),
  };
}
/** @param {import("./dashboardCreateContracts").DashboardPlan | null} plan @param {DashboardSelection | null} selection @param {string[]} ids */
function plannedSources(plan, selection, ids) {
  return plan?.sources?.length ? plan.sources : selectedForIds(selection, ids);
}
/** @param {import("./dashboardCreateContracts").DashboardPlan} plan @returns {"conflicts" | "confirm"} */
export function dashboardPlanStep(plan) {
  return (plan.conflicts ?? []).length ? "conflicts" : "confirm";
}
/** @param {{loading:boolean,error:string}} state @param {import("./dashboardCreateContracts").DashboardCreateRoute} route @param {DashboardSelection | null} selection @param {string[]} ids */
export function dashboardCreationStage(state, route, selection, ids) {
  const ready = !state.loading && !state.error;
  return {
    hasSelection: Boolean(selection) && ids.length > 0,
    showConflicts: ready && route.step === "conflicts",
    showConfirmation: ready && route.step === "confirm",
  };
}

/** @param {{name:string,reason:string}} form @param {boolean} isVersionCreation */
export function hasDashboardCreationReason(form, isVersionCreation) {
  return Boolean((isVersionCreation || form.name.trim()) && form.reason.trim());
}
