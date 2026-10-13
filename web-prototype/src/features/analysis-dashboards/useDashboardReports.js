import { useDataRefresh } from "../../hooks/useDataRefresh";
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
        // 轮询可能已读到完成状态，迟到的列表响应不能把同一报告退回运行中。
        setReports((current) => ({
          loading: false,
          error: "",
          items: reportItems.map((item) => {
            const previous = current.items.find((value) => value.id === item.id);
            return previous &&
              ["completed", "failed", "cancelled"].includes(previous.status) &&
              ["queued", "running"].includes(item.status)
              ? previous
              : item;
          }),
        }));
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

    return () => {
      reportGenerationRef.current += 1;
      reportControllerRef.current?.abort();
    };
  }, [loadReports, route.tab, route.versionId]);

  useDataRefresh(() => loadReports(true), {
    enabled: route.tab === "report" && Boolean(route.versionId),
    domains: ["analysis-dashboards"],
    identity: `${route.dashboardId}:${route.versionId}`,
    loading: reports.loading,
  });
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
