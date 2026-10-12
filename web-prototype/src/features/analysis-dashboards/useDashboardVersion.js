import { useDataRefresh } from "../../hooks/useDataRefresh";
import { useProtectedData } from "../../hooks/useProtectedData";
import {
  useCallback,
  useEffect,
  useEffectEvent,
  useMemo,
  useRef,
  useState,
} from "react";
import { dashboardApi } from "../../shared/api/dashboardApi";
import { asItems, dashboardVersionId } from "./DashboardDetailHelpers";
import { errorName, errorMessage } from "./dashboardRequestErrors";

/** @typedef {import("./dashboardDetailContracts").Dashboard} Dashboard */
/** @typedef {import("./dashboardDetailContracts").DashboardVersion} DashboardVersion */
/** @typedef {import("./dashboardDetailContracts").DashboardDetailProps} DashboardDetailProps */

/** @param {DashboardDetailProps & {protectedOperation?: boolean}} props */
export function useDashboardVersion({
  route,
  updateRoute,
  protectedOperation = false,
}) {
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

  const historyVersion = route.tab === "history" ? route.versionId : "";
  const loadMain = useCallback(
    async (background = false) => {
      const generation = mainGenerationRef.current + 1;
      mainGenerationRef.current = generation;
      mainControllerRef.current?.abort();
      const controller = new AbortController();
      mainControllerRef.current = controller;
      if (!background) setMain((current) => ({ ...current, loading: true, error: "" }));
      try {
        /** @type {[Dashboard, DashboardVersion[] | {items?: DashboardVersion[]}]} */
        const [dashboard, versionsResponse] = await Promise.all([
          dashboardApi.analysisDashboard(route.dashboardId, historyVersion, {
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
    },
    [route.dashboardId, historyVersion],
  );

  useEffect(() => {
    loadMain();
    return () => {
      mainGenerationRef.current += 1;
      mainControllerRef.current?.abort();
    };
  }, [loadMain]);
  const displayed = useProtectedData(
    main,
    protectedOperation,
    JSON.stringify([
      route.dashboardId,
      route.tab === "history" ? route.versionId : "live",
    ]),
  );
  useDataRefresh(() => loadMain(true), {
    enabled: route.tab !== "history",
    domains: ["analysis-dashboards"],
    identity: route.dashboardId,
  });
  const applyLatestVersion = useEffectEvent(() => {
    if (!displayed.dashboard) return;
    const id = initialDashboardVersion(
      route.tab === "history" ? route.versionId : "",
      displayed.dashboard,
      displayed.versions,
    );
    if (id && id !== route.versionId) updateRoute({ versionId: id }, { replace: true });
  });
  useEffect(
    () => applyLatestVersion(),
    [displayed.dashboard, displayed.versions, route.tab],
  );

  const selectedVersion = useMemo(
    () =>
      (route.tab === "history" &&
        displayed.versions.find(
          (version) => dashboardVersionId(version) === route.versionId,
        )) ||
      displayed.dashboard?.version ||
      null,
    [displayed.dashboard, displayed.versions, route.versionId, route.tab],
  );
  return { main: displayed, selectedVersion, loadMain };
}

/** @param {string} versionId @param {Dashboard} dashboard @param {DashboardVersion[]} versions */
function initialDashboardVersion(versionId, dashboard, versions) {
  return (
    versionId || dashboard.current_version_id || dashboardVersionId(versions[0] || {})
  );
}
