/** @typedef {import("./dashboardDetailContracts").DashboardVersion} DashboardVersion */
/** @typedef {import("./dashboardDetailContracts").InsightReport} InsightReport */

/** @param {InsightReport} report */
function decisionIssues(report) {
  const content = report.content;
  return content && "issues" in content && Array.isArray(content.issues)
    ? content.issues
    : [];
}

/** @param {InsightReport} report @param {string} selectedId */
export function selectedDashboardIssue(report, selectedId) {
  const issues =
    report.prompt_version === "ai-return-insight-v6" && report.status === "completed"
      ? decisionIssues(report)
      : [];
  return issues.find((issue) => issue.id === selectedId)?.id || issues[0]?.id || "";
}
/** @param {InsightReport | null} report @param {import("./analysisDashboardContracts").DashboardVersion | null} version */
export function dashboardReportSummary(report, version) {
  return report?.evidence?.analysis?.summary || version?.summary || {};
}
