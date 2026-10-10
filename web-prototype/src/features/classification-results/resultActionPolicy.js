import { isDashboardSelectable } from "./resultStatePolicy";

export {
  isDashboardSelectable,
  resultState,
  resultStateLabel,
  resultVersionId,
} from "./resultStatePolicy";

/** @typedef {import("./resultStatePolicy").ResultPolicyInput} ResultPolicyInput */

/** @param {ResultPolicyInput} result */
export function resultActionPolicy(result) {
  const published = result?.publish_status === "published";
  const dashboardSelectable = isDashboardSelectable(result);
  return {
    state: published ? "ready" : "unknown",
    label: published ? "已发布" : "未发布",
    dashboardSelectable,
    primary: {
      kind: "create-dashboard",
      label: "创建分析看板",
      disabled: !dashboardSelectable,
    },
    secondary: null,
    blockingReason: published ? "" : "分类结果版本尚未发布",
  };
}
