import { useState } from "react";
import { dashboardApi } from "../../shared/api/dashboardApi";
import { errorMessage } from "./dashboardRequestErrors";

/** @typedef {import("./analysisDashboardContracts").Dashboard} Dashboard */
/** @typedef {import("./analysisDashboardContracts").DashboardSource} DashboardSource */
/** @typedef {{name: string, sources: DashboardSource[], statuses: string[], filters: Record<string, string | string[] | null>}} DashboardSettings */

/** @param {Dashboard} dashboard @param {DashboardSource[]} sources @returns {DashboardSettings} */
export function dashboardSettings(dashboard, sources) {
  const filters = dashboard.version?.filters ?? {};
  return {
    name: dashboard.name ?? "",
    sources,
    statuses: Array.isArray(filters.quality_status)
      ? filters.quality_status
      : ["ready"],
    filters,
  };
}

/** @param {DashboardSettings} settings */
export function settingsValues(settings) {
  return {
    name: settings.name.trim(),
    sources: settings.sources.map((source) => source.result_version_id).sort(),
    statuses: [...settings.statuses].sort(),
    date_from: settings.filters.date_from || "",
    date_to: settings.filters.date_to || "",
  };
}

/** @param {DashboardSettings} settings */
export function settingsKey(settings) {
  return JSON.stringify(settingsValues(settings));
}

/** @param {Dashboard} dashboard */
export function useDashboardSettingsConflict(dashboard) {
  const [original, setOriginal] = useState(() => dashboardSettings(dashboard, []));
  const [revision, setRevision] = useState(dashboard.revision);
  const [conflict, setConflict] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [latest, setLatest] = useState(
    /** @type {{dashboard: Dashboard, settings: DashboardSettings} | null} */ (null),
  );
  const loadLatest = async () => {
    if (loading) return;
    setLoading(true);
    setLatest(null);
    setError("");
    try {
      const current = await dashboardApi.analysisDashboard(dashboard.id);
      const sources = await dashboardApi.analysisDashboardSources(
        dashboard.id,
        current.current_version_id,
      );
      setLatest({ dashboard: current, settings: dashboardSettings(current, sources) });
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setLoading(false);
    }
  };
  return {
    original,
    setOriginal,
    revision,
    conflict,
    loading,
    error,
    latest,
    loadLatest,
    requireReview: () => {
      setConflict(true);
      setLatest(null);
      setError("");
    },
    acceptLatest: () => {
      if (!latest) return;
      setOriginal(latest.settings);
      setRevision(latest.dashboard.revision);
      setConflict(false);
      setLatest(null);
    },
  };
}
