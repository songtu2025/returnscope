import { request } from "./request";

/** @param {"result" | "dashboard" | "report"} kind @param {string} id @param {"delete" | "restore"} action @param {number} revision */
export function changeDeliveryLifecycle(kind, id, action, revision) {
  const path = {
    result: "classification-results",
    dashboard: "analysis-dashboards",
    report: "ai-insight-reports",
  }[kind];
  return request(`/api/${path}/${id}/lifecycle`, {
    method: "POST",
    body: JSON.stringify({ action, expected_revision: revision }),
  });
}

/** @param {string} id */
export function cancelInsightGeneration(id) {
  return request(`/api/ai-insight-reports/${id}/cancel`, { method: "POST" });
}
