import { API_BASE, queryString, request } from "./request";

export const resultApi = {
  classificationResults: (filters = {}, options = {}) =>
    request(`/api/classification-results${queryString(filters)}`, options),
  classificationResult: (versionId, options = {}) =>
    request(`/api/classification-results/${versionId}`, options),
  classificationResultVersions: (versionId, options = {}) =>
    request(`/api/classification-results/${versionId}/versions`, options),
  classificationResultSummary: (versionId, options = {}) =>
    request(`/api/classification-results/${versionId}/summary`, options),
  classificationResultRecords: (versionId, filters = {}, options = {}) =>
    request(
      `/api/classification-results/${versionId}/records${queryString(filters)}`,
      options,
    ),
  classificationResultDrilldown: (versionId, groupBy, filters = {}, options = {}) =>
    request(
      `/api/classification-results/${versionId}/drilldown${queryString({
        group_by: groupBy,
        ...filters,
      })}`,
      options,
    ),
  classificationResultDownloadUrl: (versionId) =>
    `${API_BASE}/api/classification-results/${versionId}/download`,
};
