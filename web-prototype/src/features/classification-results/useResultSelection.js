import { useEffect, useMemo, useState } from "react";
import { navigateHash } from "../../app/hashRouter";
import {
  createDashboardSelection,
  readDashboardSelection,
  selectionItem,
  updateDashboardSelection,
} from "../analysis-dashboards/dashboardSelectionStorage";
import {
  isDashboardSelectable,
  resultActionPolicy,
  resultVersionId,
} from "./resultActionPolicy";

/** @typedef {import("./classificationResultListContracts").ClassificationResultVersion} ClassificationResultVersion */
/** @typedef {import("./classificationResultListContracts").DashboardSelectionItem} DashboardSelectionItem */
/** @typedef {import("./classificationResultListContracts").DashboardSelection} DashboardSelection */
/** @typedef {import("./classificationResultListContracts").ClassificationResultListProps} ClassificationResultListProps */

/** @param {DashboardSelectionItem[]} selected */
function selectedResultTotals(selected) {
  return selected.reduce(
    (total, item) => ({
      records: total.records + Number(item.record_count || 0),
      units: total.units + Number(item.unit_count || 0),
    }),
    { records: 0, units: 0 },
  );
}
/** @param {Pick<ClassificationResultListProps,"route"|"updateRoute"|"userId">} props */
export function useResultSelection({ route, updateRoute, userId }) {
  const [selection, setSelection] = useState(
    /** @returns {DashboardSelection | null} */ () =>
      readDashboardSelection(userId, route.selectionToken),
  );
  useEffect(() => {
    setSelection(readDashboardSelection(userId, route.selectionToken));
  }, [route.selectionToken, userId]);

  const startSelection = () => {
    const token = createDashboardSelection(userId, { intent: "dashboard" });
    updateRoute({ selectionToken: token, page: 1 });
  };

  const selectedResults = useMemo(() => selection?.selected ?? [], [selection]);
  const selectionIntent = selection?.intent ?? "dashboard";
  const selectedIds = useMemo(
    () => new Set(selectedResults.map((item) => item.result_version_id)),
    [selectedResults],
  );
  const selectedTotals = useMemo(
    () => selectedResultTotals(selectedResults),
    [selectedResults],
  );

  /** @param {ClassificationResultVersion} result */
  const toggleSelection = (result) => {
    if (!isDashboardSelectable(result)) return;
    if (!route.selectionToken) {
      const token = createDashboardSelection(userId, {
        intent: "insight",
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

  const continueToDashboard = () => {
    navigateHash("analysis-dashboards", {
      selection_token: route.selectionToken,
      step: "check",
    });
  };

  /** @param {ClassificationResultVersion} result */
  const createDashboardFromResult = (result) => {
    const token = createDashboardSelection(userId, {
      selected: [selectionItem(result)],
    });
    navigateHash("analysis-dashboards", { selection_token: token, step: "check" });
  };

  /** @param {ClassificationResultVersion} result */
  const runPrimaryAction = (result) => {
    const policy = resultActionPolicy(result, { taskId: route.taskId });
    if (policy.primary.kind === "create-dashboard") {
      createDashboardFromResult(result);
      return;
    }
    if (policy.primary.kind === "repair-source") {
      navigateHash("analysis-tasks", {
        task_id: policy.primary.taskId,
        segment_id: route.segmentId,
      });
      return;
    }
    updateRoute({
      version: resultVersionId(result),
      tab: policy.primary.kind === "create-review" ? "history" : "records",
      action: policy.primary.kind === "create-review" ? "review" : "",
      recordPage: 1,
      problem: "",
      productName: "",
      productSku: "",
      orderId: "",
    });
  };

  return {
    selectionIntent,
    selectedResults,
    selectedIds,
    selectedTotals,
    startSelection,
    toggleSelection,
    clearSelection,
    continueToDashboard,
    runPrimaryAction,
  };
}
