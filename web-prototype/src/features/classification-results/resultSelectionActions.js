import { navigateHash } from "../../app/hashRouter";
import {
  createDashboardSelection,
  selectionItem,
} from "../analysis-dashboards/dashboardSelectionStorage";
import { isDashboardSelectable } from "./resultActionPolicy";

/**
 * @param {string} userId
 * @param {Parameters<typeof import("../analysis-dashboards/dashboardSelectionStorage").selectionItem>[0]} result
 */
export function createResultDashboard(userId, result) {
  const token = createDashboardSelection(userId, { selected: [selectionItem(result)] });
  navigateHash("analysis-dashboards", { selection_token: token, step: "check" });
}

/**
 * @param {import("./classificationResultListContracts").ClassificationResultVersion} result
 * @param {{userId: string}} context
 */
export function runResultPrimaryAction(result, { userId }) {
  if (isDashboardSelectable(result)) createResultDashboard(userId, result);
}
