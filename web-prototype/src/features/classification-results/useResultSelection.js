import { useEffect, useMemo, useState } from "react";
import { navigateHash } from "../../app/hashRouter";
import {
  createDashboardSelection,
  readDashboardSelection,
  selectionItem,
  updateDashboardSelection,
} from "../analysis-dashboards/dashboardSelectionStorage";
import { isDashboardSelectable, resultVersionId } from "./resultActionPolicy";
import { runResultPrimaryAction } from "./resultSelectionActions";

/** @typedef {import("./classificationResultListContracts").ClassificationResultVersion} ClassificationResultVersion */
/** @typedef {import("./classificationResultListContracts").DashboardSelection} DashboardSelection */
/** @typedef {import("./classificationResultListContracts").ClassificationResultListProps} ClassificationResultListProps */

/** @param {Pick<ClassificationResultListProps,"route"|"updateRoute"|"userId">} props */
export function useResultSelection({ route, updateRoute, userId }) {
  const [selection, setSelection] = useState(
    /** @returns {DashboardSelection | null} */ () =>
      readDashboardSelection(userId, route.selectionToken),
  );
  useEffect(() => {
    setSelection(readDashboardSelection(userId, route.selectionToken));
  }, [route.selectionToken, userId]);

  const selectedResults = useMemo(() => selection?.selected ?? [], [selection]);
  const isVersionCreation = Boolean(selection?.target_dashboard_id);
  const selectedIds = useMemo(
    () => new Set(selectedResults.map((item) => item.result_version_id)),
    [selectedResults],
  );

  /** @param {ClassificationResultVersion} result */
  const toggleSelection = (result) => {
    if (!isDashboardSelectable(result)) return;
    if (!route.selectionToken) {
      const token = createDashboardSelection(userId, {
        selected: [selectionItem(result)],
      });
      setSelection(readDashboardSelection(userId, token));
      updateRoute({ selectionToken: token, page: 1 });
      return;
    }
    const id = resultVersionId(result);
    /** @param {DashboardSelection} current */
    const updateSelection = (current) => {
      const selected = current.selected.some((item) => item.result_version_id === id)
        ? current.selected.filter((item) => item.result_version_id !== id)
        : [...current.selected, selectionItem(result)];
      return { ...current, selected, resolved_result_version_ids: [] };
    };
    const next = updateDashboardSelection(
      userId,
      route.selectionToken,
      updateSelection,
    );
    setSelection(next);
  };

  const clearSelection = (exit = false) => {
    /** @param {DashboardSelection} current */
    const updateSelection = (current) => ({
      ...current,
      selected: [],
      resolved_result_version_ids: [],
    });
    const next = updateDashboardSelection(
      userId,
      route.selectionToken,
      updateSelection,
    );
    setSelection(next);
    if (exit) updateRoute({ selectionToken: "" });
  };

  /** @param {"dashboard" | "insight"} intent */
  const continueToCreation = (intent) => {
    if (!selectedResults.length) return;
    const next = updateDashboardSelection(userId, route.selectionToken, (current) => ({
      ...current,
      intent: isVersionCreation ? "dashboard" : intent,
    }));
    setSelection(next);
    navigateHash("analysis-dashboards", {
      selection_token: route.selectionToken,
      step: "check",
    });
  };

  /** @param {ClassificationResultVersion} result */
  const runPrimaryAction = (result) =>
    runResultPrimaryAction(result, { route, updateRoute, userId });

  return {
    isVersionCreation,
    selectedResults,
    selectedIds,
    toggleSelection,
    clearSelection,
    continueToDashboard: () => continueToCreation("dashboard"),
    continueToInsight: () => continueToCreation("insight"),
    runPrimaryAction,
  };
}
