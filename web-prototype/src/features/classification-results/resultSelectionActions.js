import { navigateHash } from "../../app/hashRouter";
import {
  createDashboardSelection,
  selectionItem,
} from "../analysis-dashboards/dashboardSelectionStorage";
import { resultActionPolicy, resultVersionId } from "./resultActionPolicy";

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
 * @param {Pick<import("./classificationResultListContracts").ClassificationResultListProps, "route" | "updateRoute" | "userId">} context
 */
export function runResultPrimaryAction(result, { route, updateRoute, userId }) {
  const policy = resultActionPolicy(result, { taskId: route.taskId });
  if (policy.primary.kind === "create-dashboard") {
    createResultDashboard(userId, result);
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
}
