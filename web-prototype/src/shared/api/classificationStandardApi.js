import { API_BASE, request } from "./request";

export const classificationStandardApi = {
  classificationStandards: () => request("/api/classification-standards"),
  createClassificationStandard: (payload) =>
    request("/api/classification-standards", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  classificationStandard: (standardId) =>
    request(`/api/classification-standards/${standardId}`),
  deleteClassificationStandard: (standardId) =>
    request(`/api/classification-standards/${standardId}`, {
      method: "DELETE",
    }),
  classificationStandardVersions: (standardId) =>
    request(`/api/classification-standards/${standardId}/versions`),
  classificationStandardVersionExportUrl: (versionId) =>
    `${API_BASE}/api/classification-standard-versions/${versionId}/export`,
  restoreClassificationStandardVersion: (versionId) =>
    request(`/api/classification-standard-versions/${versionId}/restore-draft`, {
      method: "POST",
    }),
  classificationStandardDraft: (draftId) =>
    request(`/api/classification-standard-drafts/${draftId}`),
  previewClassificationExcel: (draftId, file, sheetName = "", columns = {}) => {
    const body = new FormData();
    body.append("file", file);
    body.append("sheet_name", sheetName);
    body.append("columns_json", JSON.stringify(columns));
    return request(`/api/classification-standard-drafts/${draftId}/preview-excel`, {
      method: "POST",
      body,
    });
  },
  createClassificationStandardDraft: (standardId) =>
    request(`/api/classification-standards/${standardId}/draft`, {
      method: "POST",
    }),
  updateClassificationStandardDraft: (draftId, payload) =>
    request(`/api/classification-standard-drafts/${draftId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  importClassificationStandardDraft: (draftId, payload) =>
    request(`/api/classification-standard-drafts/${draftId}/import`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  validateClassificationStandardDraft: (draftId, expectedRevision) =>
    request(`/api/classification-standard-drafts/${draftId}/validate`, {
      method: "POST",
      body: JSON.stringify({ expected_revision: expectedRevision }),
    }),
  publishClassificationStandardDraft: (draftId, payload) =>
    request(`/api/classification-standard-drafts/${draftId}/publish`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  discardClassificationStandardDraft: (draftId, payload) =>
    request(`/api/classification-standard-drafts/${draftId}/discard`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  classificationStandardValidationSources: (draftId) =>
    request(`/api/classification-standard-drafts/${draftId}/validation-sources`),
  classificationStandardValidationRuns: (draftId) =>
    request(`/api/classification-standard-drafts/${draftId}/validation-runs`),
  createClassificationStandardValidationRun: (draftId, payload) =>
    request(`/api/classification-standard-drafts/${draftId}/validation-runs`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  createReviewStandardValidationRun: (
    draftId,
    file,
    revision,
    sampleSize,
    comparisonType = "standard_version",
  ) => {
    const body = new FormData();
    body.append("file", file);
    body.append("expected_revision", revision);
    body.append("sample_size", sampleSize);
    body.append("comparison_type", comparisonType);
    return request(
      `/api/classification-standard-drafts/${draftId}/review-validation-runs`,
      {
        method: "POST",
        body,
      },
    );
  },
  classificationStandardValidationRun: (runId) =>
    request(`/api/classification-standard-validation-runs/${runId}`),
  approveClassificationStandardValidationRun: (runId, payload) =>
    request(`/api/classification-standard-validation-runs/${runId}/approve`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  resultTaxonomy: (resultVersionId, options = {}) =>
    request(`/api/classification-results/${resultVersionId}/taxonomy`, options),
};
