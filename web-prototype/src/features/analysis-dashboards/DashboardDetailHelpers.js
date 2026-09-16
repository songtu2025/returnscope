/** @typedef {import("./analysisDashboardContracts").DashboardVersion} DashboardVersion */
/** @typedef {import("./analysisDashboardContracts").InsightReport} InsightReport */

/** @param {DashboardVersion} version */
export function dashboardVersionId(version) {
  return version.version_id || version.id || "";
}

/** @template T @param {T[] | {items?: T[]} | null | undefined} value @returns {T[]} */
export function asItems(value) {
  return Array.isArray(value) ? value : (value?.items ?? []);
}

/** @param {InsightReport} report */
export function isPublishedReport(report) {
  return report.status === "completed" && Boolean(report.version_no);
}
