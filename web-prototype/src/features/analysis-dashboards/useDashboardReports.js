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

  const loadReports = useCallback(
    /** @param {boolean} [silent] */ async (silent = false) => {
      if (route.tab !== "report" || !route.versionId) {
        setReports({ loading: false, error: "", items: [] });
        return;
      }
      const generation = reportGenerationRef.current + 1;
      reportGenerationRef.current = generation;
      reportControllerRef.current?.abort();
      const controller = new AbortController();
      reportControllerRef.current = controller;
      setReports((current) => ({
        ...current,
        loading: silent === true ? current.loading : true,
        error: "",
      }));
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
    },
    [route.dashboardId, route.tab, route.versionId],
  );

  useEffect(() => {
    loadReports();
    const refresh = () => {
      if (!document.hidden && route.tab === "report" && route.versionId)
        loadReports(true);
    };
    const timer =
      route.tab === "report" && route.versionId
        ? window.setInterval(refresh, 10000)
        : null;
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      reportGenerationRef.current += 1;
      reportControllerRef.current?.abort();
      if (timer !== null) window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [loadReports, route.tab, route.versionId]);

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
