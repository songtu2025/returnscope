import { queryString, request } from "./request";

function jsonRequest(path, method, payload, options = {}) {
  return request(path, {
    ...options,
    method,
    body: JSON.stringify(payload),
  });
}

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
};
