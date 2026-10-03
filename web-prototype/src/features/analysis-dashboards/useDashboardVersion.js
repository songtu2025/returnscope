import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { dashboardApi } from "../../shared/api/dashboardApi";
import { asItems, dashboardVersionId } from "./DashboardDetailHelpers";
import { errorName, errorMessage } from "./dashboardRequestErrors";

/** @typedef {import("./dashboardDetailContracts").Dashboard} Dashboard */
/** @typedef {import("./dashboardDetailContracts").DashboardVersion} DashboardVersion */
/** @typedef {import("./dashboardDetailContracts").DashboardDetailProps} DashboardDetailProps */

/** @param {DashboardDetailProps} props */
export function useDashboardVersion({ route, updateRoute }) {
  const [main, setMain] = useState(
    /** @returns {{loading: boolean, error: string, dashboard: Dashboard | null, versions: DashboardVersion[]}} */ () => ({
      loading: true,
      error: "",
      dashboard: null,
      versions: [],
    }),
  );
  const mainGenerationRef = useRef(0);
  /** @type {import("react").RefObject<AbortController | null>} */
  const mainControllerRef = useRef(null);

  const loadMain = useCallback(async () => {
    const generation = mainGenerationRef.current + 1;
    mainGenerationRef.current = generation;
    mainControllerRef.current?.abort();
    const controller = new AbortController();
    mainControllerRef.current = controller;
    setMain((current) => ({ ...current, loading: true, error: "" }));
    try {
      /** @type {[Dashboard, DashboardVersion[] | {items?: DashboardVersion[]}]} */
      const [dashboard, versionsResponse] = await Promise.all([
        dashboardApi.analysisDashboard(route.dashboardId, route.versionId, {
          signal: controller.signal,
        }),
        dashboardApi.analysisDashboardVersions(route.dashboardId, {
          signal: controller.signal,
        }),
      ]);
      if (mainGenerationRef.current !== generation) return;
      /** @type {DashboardVersion[]} */
      const versions = asItems(versionsResponse);
      setMain({ loading: false, error: "", dashboard, versions });
      const selectedVersionId = initialDashboardVersion(
        route.versionId,
        dashboard,
        versions,
      );
      if (selectedVersionId && selectedVersionId !== route.versionId) {
        updateRoute({ versionId: selectedVersionId }, { replace: true });
      }
    } catch (error) {
      if (
        mainGenerationRef.current === generation &&
        errorName(error) !== "AbortError"
      ) {
        setMain((current) => ({
          ...current,
          loading: false,
          error: errorMessage(error),
        }));
      }
    }
  }, [route.dashboardId, route.versionId, updateRoute]);

  useEffect(() => {
    loadMain();
    return () => {
      mainGenerationRef.current += 1;
      mainControllerRef.current?.abort();
    };
  }, [loadMain]);

  const selectedVersion = useMemo(
    () =>
      main.versions.find(
        (version) => dashboardVersionId(version) === route.versionId,
      ) ||
      main.dashboard?.version ||
      null,
    [main.dashboard, main.versions, route.versionId],
  );
  return { main, selectedVersion, loadMain };
}

/** @param {string} versionId @param {Dashboard} dashboard @param {DashboardVersion[]} versions */
function initialDashboardVersion(versionId, dashboard, versions) {
  return (
    versionId || dashboard.current_version_id || dashboardVersionId(versions[0] || {})
  );
}
