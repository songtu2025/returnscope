import { queryString, request } from "./request";

/** @typedef {object} DashboardPayload */
/** @typedef {Record<string, unknown>} DashboardQuery */
/** @typedef {ReturnType<typeof request>} DashboardRequest */

/**
 * @param {string} path
 * @param {string} method
 * @param {DashboardPayload} payload
 * @param {RequestInit} [options]
 */
function jsonRequest(path, method, payload, options = {}) {
  return request(path, {
    ...options,
    method,
    body: JSON.stringify(payload),
  });
}

/**
 * @type {{
 *   dashboardPreflight: (payload: DashboardPayload, options?: RequestInit) => DashboardRequest,
 *   createAnalysisDashboard: (payload: DashboardPayload, options?: RequestInit) => DashboardRequest,
 *   createAnalysisDashboardVersion: (dashboardId: string, payload: DashboardPayload, options?: RequestInit) => DashboardRequest,
 *   analysisDashboards: (filters?: DashboardQuery, options?: RequestInit) => DashboardRequest,
 *   analysisDashboard: (dashboardId: string, versionId?: string, options?: RequestInit) => DashboardRequest,
 *   analysisDashboardVersions: (dashboardId: string, options?: RequestInit) => DashboardRequest,
 *   analysisDashboardSummary: (dashboardId: string, versionId: string, options?: RequestInit) => DashboardRequest,
 *   analysisDashboardSources: (dashboardId: string, versionId: string, options?: RequestInit) => DashboardRequest,
 *   analysisDashboardInsights: (dashboardId: string, versionId: string, filters?: DashboardQuery, options?: RequestInit) => DashboardRequest,
 *   analysisDashboardDrilldown: (dashboardId: string, versionId: string, groupBy: string, filters?: DashboardQuery, options?: RequestInit) => DashboardRequest,
 *   analysisDashboardRecords: (dashboardId: string, versionId: string, filters?: DashboardQuery, options?: RequestInit) => DashboardRequest,
 *   createInsightReportFromResults: (payload: DashboardPayload, options?: RequestInit) => DashboardRequest,
 *   createAnalysisDashboardInsightReport: (dashboardId: string, versionId: string, payload: DashboardPayload, options?: RequestInit) => DashboardRequest,
 *   analysisDashboardInsightReports: (dashboardId: string, versionId: string, options?: RequestInit) => DashboardRequest,
 *   insightReport: (reportId: string, options?: RequestInit) => DashboardRequest,
 *   retryInsightReport: (reportId: string, options?: RequestInit) => DashboardRequest,
 *   setInsightReportIssueDecision: (reportId: string, issueId: string, status: string, options?: RequestInit) => DashboardRequest
 * }}
 */
export const dashboardApi = {
  dashboardPreflight: (payload, options = {}) =>
    jsonRequest("/api/dashboard-plans/preflight", "POST", payload, options),
  createAnalysisDashboard: (payload, options = {}) =>
    jsonRequest("/api/analysis-dashboards", "POST", payload, options),
  createAnalysisDashboardVersion: (dashboardId, payload, options = {}) =>
    jsonRequest(
      `/api/analysis-dashboards/${dashboardId}/versions`,
      "POST",
      payload,
      options,
    ),
  analysisDashboards: (filters = {}, options = {}) =>
    request(`/api/analysis-dashboards${queryString(filters)}`, options),
  analysisDashboard: (dashboardId, versionId = "", options = {}) =>
    request(
      `/api/analysis-dashboards/${dashboardId}${queryString({ version_id: versionId })}`,
      options,
    ),
  analysisDashboardVersions: (dashboardId, options = {}) =>
    request(`/api/analysis-dashboards/${dashboardId}/versions`, options),
  analysisDashboardSummary: (dashboardId, versionId, options = {}) =>
    request(
      `/api/analysis-dashboards/${dashboardId}/versions/${versionId}/summary`,
      options,
    ),
  analysisDashboardSources: (dashboardId, versionId, options = {}) =>
    request(
      `/api/analysis-dashboards/${dashboardId}/versions/${versionId}/sources`,
      options,
    ),
  analysisDashboardInsights: (dashboardId, versionId, filters = {}, options = {}) =>
    request(
      `/api/analysis-dashboards/${dashboardId}/versions/${versionId}/insights${queryString(
        filters,
      )}`,
      options,
    ),
  analysisDashboardDrilldown: (
    dashboardId,
    versionId,
    groupBy,
    filters = {},
    options = {},
  ) =>
    request(
      `/api/analysis-dashboards/${dashboardId}/versions/${versionId}/drilldown${queryString(
        { group_by: groupBy, ...filters },
      )}`,
      options,
    ),
  analysisDashboardRecords: (dashboardId, versionId, filters = {}, options = {}) =>
    request(
      `/api/analysis-dashboards/${dashboardId}/versions/${versionId}/records${queryString(
        filters,
      )}`,
      options,
    ),
  createInsightReportFromResults: (payload, options = {}) =>
    jsonRequest("/api/ai-insight-reports/from-results", "POST", payload, options),
  createAnalysisDashboardInsightReport: (
    dashboardId,
    versionId,
    payload,
    options = {},
  ) =>
    jsonRequest(
      `/api/analysis-dashboards/${dashboardId}/versions/${versionId}/ai-insight-reports`,
      "POST",
      payload,
      options,
    ),
  analysisDashboardInsightReports: (dashboardId, versionId, options = {}) =>
    request(
      `/api/analysis-dashboards/${dashboardId}/ai-insight-reports${queryString({
        version_id: versionId,
      })}`,
      options,
    ),
  insightReport: (reportId, options = {}) =>
    request(`/api/ai-insight-reports/${reportId}`, options),
  retryInsightReport: (reportId, options = {}) =>
    jsonRequest(`/api/ai-insight-reports/${reportId}/retry`, "POST", {}, options),
  setInsightReportIssueDecision: (reportId, issueId, status, options = {}) =>
    jsonRequest(
      `/api/ai-insight-reports/${reportId}/issues/${encodeURIComponent(issueId)}/decision`,
      "PUT",
      { status },
      options,
    ),
};
