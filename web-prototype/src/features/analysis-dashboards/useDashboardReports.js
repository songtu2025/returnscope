import { useCallback, useEffect, useRef, useState } from "react";
import { dashboardApi } from "../../shared/api/dashboardApi";
import { asItems } from "./DashboardDetailHelpers";
import { errorName, errorMessage } from "./dashboardRequestErrors";
import {
  useDashboardReportSelection,
  useDashboardReportPolling,
} from "./dashboardReportLifecycle";

/** @typedef {import("./dashboardDetailContracts").InsightReport} InsightReport */
/** @typedef {import("./dashboardDetailContracts").DashboardDetailProps} DashboardDetailProps */

/** @param {Pick<DashboardDetailProps, "route">} props */
function useReportList({ route }) {
  const [reports, setReports] = useState(
    /** @returns {import("./dashboardReportLifecycle").DashboardReportState} */ () => ({
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

  return { reports, setReports, loadReports };
}

/** @param {DashboardDetailProps} props */
export function useDashboardReports({ route, updateRoute, notify }) {
  const { reports, setReports, loadReports } = useReportList({ route });
  const {
    publishedReports,
    generationAttempts,
    latestPublishedReport,
    selectedReport,
  } = useDashboardReportSelection({ route, updateRoute, reports });
  useDashboardReportPolling({ generationAttempts, setReports, notify });
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
