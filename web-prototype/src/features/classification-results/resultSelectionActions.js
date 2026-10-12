import { navigateHash } from "../../app/hashRouter";
import {
  createDashboardSelection,
  selectionItem,
} from "../analysis-dashboards/dashboardSelectionStorage";
import { isDashboardSelectable } from "./resultActionPolicy";
import { classificationResultPoolQuery } from "./classificationResultRoute";

/**
 * @param {string} userId
 * @param {Parameters<typeof import("../analysis-dashboards/dashboardSelectionStorage").selectionItem>[0]} result
 * @param {import("./classificationResultRoute").ClassificationResultRoute} route
 */
export function createResultDashboard(userId, result, route) {
  const token = createDashboardSelection(userId, {
    selected: [selectionItem(result)],
    result_pool_query: classificationResultPoolQuery(route),
  });
  navigateHash("analysis-dashboards", { selection_token: token, step: "check" });
}

/**
 * @param {import("./classificationResultListContracts").ClassificationResultVersion} result
 * @param {{userId: string, route: import("./classificationResultRoute").ClassificationResultRoute}} context
 */
export function runResultPrimaryAction(result, { userId, route }) {
  if (isDashboardSelectable(result)) createResultDashboard(userId, result, route);
}
