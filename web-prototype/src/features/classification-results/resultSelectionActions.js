import { buildHash, navigateHash } from "../../app/hashRouter";
import {
  createDashboardSelection,
  selectionItem,
} from "../analysis-dashboards/dashboardSelectionStorage";
import { isDashboardSelectable } from "./resultActionPolicy";
import {
  classificationResultPoolQuery,
  classificationResultQuery,
} from "./classificationResultRoute";

/**
 * @param {string} userId
 * @param {Parameters<typeof import("../analysis-dashboards/dashboardSelectionStorage").selectionItem>[0] & import("./resultActionPolicy").ResultPolicyInput} result
 * @param {import("./classificationResultRoute").ClassificationResultRoute} route
 * @param {"dashboard" | "insight"} [intent]
 */
export function createResultSelection(userId, result, route, intent = "dashboard") {
  if (!isDashboardSelectable(result)) return;
  const token = createDashboardSelection(userId, {
    selected: [selectionItem(result)],
    intent,
    ...(intent === "insight"
      ? {
          result_return: buildHash(
            "classification-results",
            classificationResultQuery(route),
          ),
        }
      : {}),
    result_pool_query: classificationResultPoolQuery(route),
  });
  navigateHash("analysis-dashboards", { selection_token: token, step: "check" });
}

/**
 * @param {import("./classificationResultListContracts").ClassificationResultVersion} result
 * @param {{userId: string, route: import("./classificationResultRoute").ClassificationResultRoute}} context
 */
export function runResultPrimaryAction(result, { userId, route }) {
  createResultSelection(userId, result, route);
}
