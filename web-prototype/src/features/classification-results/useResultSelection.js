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
import { classificationResultPoolQuery } from "./classificationResultRoute";

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
  const selectedIds = useMemo(
    () => new Set(selectedResults.map((item) => item.result_version_id)),
    [selectedResults],
  );

  /** @param {(selected: DashboardSelection["selected"]) => DashboardSelection["selected"]} updater */
  const updateSelectedResults = (updater) => {
    const next = updateDashboardSelection(userId, route.selectionToken, (current) => ({
      ...current,
      selected: updater(current.selected),
      resolved_result_version_ids: [],
    }));
    setSelection(next);
  };

  /** @param {ClassificationResultVersion[]} results */
  const toggleSelections = (results) => {
    const eligible = results.filter(isDashboardSelectable);
    if (!eligible.length) return;
    const ids = new Set(eligible.map(resultVersionId));
    const allSelected = [...ids].every((id) => selectedIds.has(id));
    /** @param {DashboardSelection["selected"]} selected */
    const update = (selected) => {
      if (allSelected)
        return selected.filter((item) => !ids.has(item.result_version_id));
      const next = new Map(selected.map((item) => [item.result_version_id, item]));
      eligible.forEach((item) => next.set(resultVersionId(item), selectionItem(item)));
      return [...next.values()];
    };
    if (!route.selectionToken) {
      const token = createDashboardSelection(userId, {
        selected: update([]),
      });
      setSelection(readDashboardSelection(userId, token));
      updateRoute({ selectionToken: token });
      return;
    }
    updateSelectedResults(update);
  };
  /** @param {ClassificationResultVersion} result */
  const toggleSelection = (result) => toggleSelections([result]);

  const clearSelection = () => {
    updateSelectedResults(() => []);
  };
  /** @param {string} id */
  const removeSelection = (id) =>
    updateSelectedResults((selected) =>
      selected.filter((item) => item.result_version_id !== id),
    );

  /** @param {"dashboard" | "insight"} intent */
  const continueToCreation = (intent) => {
    if (!selectedResults.length) return;
    const next = updateDashboardSelection(userId, route.selectionToken, (current) => ({
      ...current,
      intent,
      task_return: undefined,
      result_pool_query: classificationResultPoolQuery(route),
    }));
    setSelection(next);
    navigateHash("analysis-dashboards", {
      selection_token: route.selectionToken,
      step: "check",
    });
  };

  /** @param {ClassificationResultVersion} result */
  const runPrimaryAction = (result) =>
    runResultPrimaryAction(result, { userId, route });

  return {
    selectedResults,
    selectedIds,
    toggleSelection,
    toggleSelections,
    clearSelection,
    removeSelection,
    continueToDashboard: () => continueToCreation("dashboard"),
    continueToInsight: () => continueToCreation("insight"),
    runPrimaryAction,
  };
}
