import { useCallback, useEffect, useRef, useState } from "react";
import { dashboardApi } from "../../shared/api/dashboardApi";
import { asItems, isPublishedReport } from "./DashboardDetailHelpers";
import { errorName, errorMessage } from "./dashboardRequestErrors";
import { selectedDashboardIssue } from "./dashboardReportPolicy";

/** @typedef {import("./dashboardDetailContracts").InsightReport} InsightReport */
/** @typedef {import("./dashboardDetailContracts").DashboardDetailProps} DashboardDetailProps */

/** @param {DashboardDetailProps} props */
export function useDashboardReports({ route, updateRoute, notify }) {
  const [reports, setReports] = useState(
    /** @returns {{loading: boolean, error: string, items: InsightReport[]}} */ () => ({
      loading: false,
      error: "",
      items: [],
    }),
  );
  const reportGenerationRef = useRef(0);
  /** @type {import("react").RefObject<AbortController | null>} */
  const reportControllerRef = useRef(null);

  const loadReports = useCallback(async () => {
    if (route.tab !== "report" || !route.versionId) {
      setReports({ loading: false, error: "", items: [] });
      return;
    }
    const generation = reportGenerationRef.current + 1;
    reportGenerationRef.current = generation;
    reportControllerRef.current?.abort();
    const controller = new AbortController();
    reportControllerRef.current = controller;
    setReports((current) => ({ ...current, loading: true, error: "" }));
    try {
      const items = await dashboardApi.analysisDashboardInsightReports(
        route.dashboardId,
        route.versionId,
        { signal: controller.signal },
      );
      if (reportGenerationRef.current !== generation) return;
      /** @type {InsightReport[]} */
      const reportItems = asItems(items);
      setReports({ loading: false, error: "", items: reportItems });
    } catch (error) {
      if (
        reportGenerationRef.current === generation &&
        errorName(error) !== "AbortError"
      ) {
        setReports((current) => ({
          ...current,
          loading: false,
          error: errorMessage(error),
        }));
      }
    }
  }, [route.dashboardId, route.tab, route.versionId]);

  useEffect(() => {
    loadReports();
    return () => {
      reportGenerationRef.current += 1;
      reportControllerRef.current?.abort();
    };
  }, [loadReports]);

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
  }, [activeReportId, notify]);
  return {
    reports,
    setReports,
    loadReports,
    publishedReports,
    generationAttempts,
    latestPublishedReport,
    selectedReport,
  };
}
