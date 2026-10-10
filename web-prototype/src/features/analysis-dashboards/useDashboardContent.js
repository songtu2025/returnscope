import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  completedDashboardContent,
  dashboardContentContext,
  failedDashboardContent,
  loadDashboardContent,
  pendingDashboardContent,
} from "./dashboardContentLoading";
import { errorName, errorMessage } from "./dashboardRequestErrors";

/** @typedef {import("./dashboardDetailContracts").DashboardContentState} DashboardContentState */
/** @typedef {import("./dashboardDetailContracts").DashboardRecord} DashboardRecord */
/** @typedef {import("./dashboardDetailContracts").DashboardDetailProps} DashboardDetailProps */

/** @param {DashboardDetailProps} props */
export function useDashboardContent({ route, updateRoute }) {
  const [content, setContent] = useState(
    /** @returns {DashboardContentState} */ () => ({
      ...completedDashboardContent(null),
      loading: true,
    }),
  );
  const [selectedRecord, setSelectedRecord] = useState(
    /** @returns {DashboardRecord | null} */ () => null,
  );
  const contentGenerationRef = useRef(0);
  /** @type {import("react").RefObject<AbortController | null>} */
  const contentControllerRef = useRef(null);
  /** @type {import("react").RefObject<{key: string, data: import("./analysisDashboardContracts").DashboardInsights | null}>} */
  const overviewCacheRef = useRef({ key: "", data: null });
  const filters = useMemo(
    () => ({
      problem: route.problem,
      subject: route.subject,
      label_group: route.labelGroup,
      listing: route.listing,
      product_name: route.productName,
      product_sku: route.productSku,
      date_from: route.dateFrom,
      date_to: route.dateTo,
    }),
    [
      route.dateFrom,
      route.dateTo,
      route.labelGroup,
      route.listing,
      route.problem,
      route.subject,
      route.productName,
      route.productSku,
    ],
  );
  const loadContent = useCallback(async () => {
    if (!route.versionId || ["history", "report"].includes(route.tab)) {
      setContent(completedDashboardContent(null));
      return;
    }
    const generation = contentGenerationRef.current + 1;
    contentGenerationRef.current = generation;
    contentControllerRef.current?.abort();
    const controller = new AbortController();
    contentControllerRef.current = controller;
    const contentRoute = {
      dashboardId: route.dashboardId,
      versionId: route.versionId,
      tab: route.tab,
    };
    const context = dashboardContentContext(contentRoute, filters);
    const cachedOverview =
      overviewCacheRef.current.key === context.scopeKey
        ? overviewCacheRef.current.data
        : null;
    setContent((current) => pendingDashboardContent(current, context, cachedOverview));
    try {
      const result = await loadDashboardContent({
        route: contentRoute,
        filters,
        cachedOverview,
        signal: controller.signal,
        onOverview: (overview) => {
          overviewCacheRef.current = { key: context.scopeKey, data: overview };
        },
      });
      if (contentGenerationRef.current !== generation) return;
      if ("resetCategory" in result) {
        updateRoute(
          {
            labelGroup: "",
            problem: "",
            recordPage: 1,
            reasonPage: 0,
          },
          { replace: true },
        );
        return;
      }
      setContent(completedDashboardContent(result.data, context));
    } catch (error) {
      if (
        contentGenerationRef.current === generation &&
        errorName(error) !== "AbortError"
      ) {
        setContent((current) => failedDashboardContent(current, errorMessage(error)));
      }
    }
  }, [filters, route.dashboardId, route.tab, route.versionId, updateRoute]);

  useEffect(() => {
    setSelectedRecord(null);
    loadContent();
    return () => {
      contentGenerationRef.current += 1;
      contentControllerRef.current?.abort();
    };
  }, [loadContent]);
  return { content, selectedRecord, setSelectedRecord, loadContent };
}
