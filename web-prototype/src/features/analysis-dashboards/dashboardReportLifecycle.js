import { useEffect } from "react";
import { dashboardApi } from "../../shared/api/dashboardApi";
import { isPublishedReport } from "./DashboardDetailHelpers";
import { selectedDashboardIssue } from "./dashboardReportPolicy";

/** @typedef {import("./dashboardDetailContracts").InsightReport} InsightReport */
/** @typedef {import("./dashboardDetailContracts").DashboardDetailProps} DashboardDetailProps */
/** @typedef {{loading: boolean, error: string, items: InsightReport[]}} DashboardReportState */

/** @param {Pick<DashboardDetailProps, "route" | "updateRoute"> & {reports: DashboardReportState}} props */
export function useDashboardReportSelection({ route, updateRoute, reports }) {
  const publishedReports = reports.items.filter(isPublishedReport);
  const generationAttempts = reports.items.filter(
    (report) => !isPublishedReport(report),
  );
  const latestPublishedReport = publishedReports[0] || null;
  const selectedReport =
    reports.items.find((report) => report.id === route.reportId) ||
    latestPublishedReport ||
    generationAttempts[0] ||
    null;

  useEffect(() => {
    if (route.tab !== "report" || reports.loading || reports.error || !selectedReport) {
      return;
    }
    const issueId = selectedDashboardIssue(selectedReport, route.issueId);
    if (selectedReport.id === route.reportId && issueId === route.issueId) return;
    // 一次补全报告与问题，避免两个更新互相覆盖并反复加载正文。
    updateRoute({ reportId: selectedReport.id, issueId }, { replace: true });
  }, [
    reports.error,
    reports.loading,
    route.issueId,
    route.reportId,
    route.tab,
    selectedReport,
    updateRoute,
  ]);
  return {
    publishedReports,
    generationAttempts,
    latestPublishedReport,
    selectedReport,
  };
}

/** @param {{generationAttempts: InsightReport[], setReports: import("react").Dispatch<import("react").SetStateAction<DashboardReportState>>, notify: DashboardDetailProps["notify"]}} props */
export function useDashboardReportPolling({ generationAttempts, setReports, notify }) {
  const activeReportId = generationAttempts.find((report) =>
    ["queued", "running"].includes(report.status),
  )?.id;

  useEffect(() => {
    if (!activeReportId) return undefined;
    const timer = window.setInterval(async () => {
      if (document.hidden) return;
      try {
        const updated = await dashboardApi.insightReport(activeReportId);
        setReports((current) => ({
          ...current,
          items: current.items.map((item) => (item.id === updated.id ? updated : item)),
        }));
        if (updated.status === "completed") {
          notify?.("AI 洞察报告已生成");
        } else if (updated.status === "failed") {
          notify?.("AI 洞察报告生成未完成，可在报告页重试");
        }
      } catch {
        window.clearInterval(timer);
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [activeReportId, notify, setReports]);
}
