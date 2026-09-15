import { API_BASE, request } from "./request";

/** @typedef {import("./classificationStandardContracts").ClassificationResultTaxonomy} ClassificationResultTaxonomy */
/** @typedef {import("./classificationStandardContracts").ClassificationStandardActionPayload} ClassificationStandardActionPayload */
/** @typedef {import("./classificationStandardContracts").ClassificationStandardCreatePayload} ClassificationStandardCreatePayload */
/** @typedef {import("./classificationStandardContracts").ClassificationStandardDeleteResult} ClassificationStandardDeleteResult */
/** @typedef {import("./classificationStandardContracts").ClassificationStandardDetail} ClassificationStandardDetail */
/** @typedef {import("./classificationStandardContracts").ClassificationStandardDiscardResult} ClassificationStandardDiscardResult */
/** @typedef {import("./classificationStandardContracts").ClassificationStandardDraft} ClassificationStandardDraft */
/** @typedef {import("./classificationStandardContracts").ClassificationStandardExcelColumns} ClassificationStandardExcelColumns */
/** @typedef {import("./classificationStandardContracts").ClassificationStandardExcelPreview} ClassificationStandardExcelPreview */
/** @typedef {import("./classificationStandardContracts").ClassificationStandardImportPayload} ClassificationStandardImportPayload */
/** @typedef {import("./classificationStandardContracts").ClassificationStandardSummary} ClassificationStandardSummary */
/** @typedef {import("./classificationStandardContracts").ClassificationStandardUpdatePayload} ClassificationStandardUpdatePayload */
/** @typedef {import("./classificationStandardContracts").ClassificationStandardValidationApprovalPayload} ClassificationStandardValidationApprovalPayload */
/** @typedef {import("./classificationStandardContracts").ClassificationStandardValidationRunDetail} ClassificationStandardValidationRunDetail */
/** @typedef {import("./classificationStandardContracts").ClassificationStandardValidationRunPayload} ClassificationStandardValidationRunPayload */
/** @typedef {import("./classificationStandardContracts").ClassificationStandardValidationRunSummary} ClassificationStandardValidationRunSummary */
/** @typedef {import("./classificationStandardContracts").ClassificationStandardValidationSource} ClassificationStandardValidationSource */
/** @typedef {import("./classificationStandardContracts").ClassificationStandardVersion} ClassificationStandardVersion */
/** @typedef {import("./classificationStandardContracts").ValidationComparisonType} ValidationComparisonType */
/** @typedef {import("./classificationStandardContracts").ValidationSampleSize} ValidationSampleSize */

export const classificationStandardApi = {
  /** @returns {Promise<ClassificationStandardSummary[]>} */
  classificationStandards: () => request("/api/classification-standards"),
  /**
   * @param {ClassificationStandardCreatePayload} payload
   * @returns {Promise<ClassificationStandardDraft>}
   */
  createClassificationStandard: (payload) =>
    request("/api/classification-standards", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  /** @returns {Promise<ClassificationStandardDetail>} */
  classificationStandard: (/** @type {string} */ standardId) =>
    request(`/api/classification-standards/${standardId}`),
  /** @returns {Promise<ClassificationStandardDeleteResult>} */
  deleteClassificationStandard: (/** @type {string} */ standardId) =>
    request(`/api/classification-standards/${standardId}`, {
      method: "DELETE",
    }),
  /** @returns {Promise<ClassificationStandardVersion[]>} */
  classificationStandardVersions: (/** @type {string} */ standardId) =>
    request(`/api/classification-standards/${standardId}/versions`),
  classificationStandardVersionExportUrl: (/** @type {string} */ versionId) =>
    `${API_BASE}/api/classification-standard-versions/${versionId}/export`,
  /** @returns {Promise<ClassificationStandardDraft>} */
  restoreClassificationStandardVersion: (/** @type {string} */ versionId) =>
    request(`/api/classification-standard-versions/${versionId}/restore-draft`, {
      method: "POST",
    }),
  /** @returns {Promise<ClassificationStandardDraft>} */
  classificationStandardDraft: (/** @type {string} */ draftId) =>
    request(`/api/classification-standard-drafts/${draftId}`),
  /** @returns {Promise<ClassificationStandardExcelPreview>} */
  previewClassificationExcel: (
    /** @type {string} */ draftId,
    /** @type {File} */ file,
    /** @type {string} */ sheetName = "",
    /** @type {ClassificationStandardExcelColumns} */ columns = {},
  ) => {
    const body = new FormData();
    body.append("file", file);
    body.append("sheet_name", sheetName);
    body.append("columns_json", JSON.stringify(columns));
    return request(`/api/classification-standard-drafts/${draftId}/preview-excel`, {
      method: "POST",
      body,
    });
  },
  /** @returns {Promise<ClassificationStandardDraft>} */
  createClassificationStandardDraft: (/** @type {string} */ standardId) =>
    request(`/api/classification-standards/${standardId}/draft`, {
      method: "POST",
    }),
  /** @returns {Promise<ClassificationStandardDraft>} */
  updateClassificationStandardDraft: (
    /** @type {string} */ draftId,
    /** @type {ClassificationStandardUpdatePayload} */ payload,
  ) =>
    request(`/api/classification-standard-drafts/${draftId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  /** @returns {Promise<ClassificationStandardDraft>} */
  importClassificationStandardDraft: (
    /** @type {string} */ draftId,
    /** @type {ClassificationStandardImportPayload} */ payload,
  ) =>
    request(`/api/classification-standard-drafts/${draftId}/import`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  /** @returns {Promise<ClassificationStandardDraft>} */
  validateClassificationStandardDraft: (
    /** @type {string} */ draftId,
    /** @type {number} */ expectedRevision,
  ) =>
    request(`/api/classification-standard-drafts/${draftId}/validate`, {
      method: "POST",
      body: JSON.stringify({ expected_revision: expectedRevision }),
    }),
  /** @returns {Promise<ClassificationStandardDetail>} */
  publishClassificationStandardDraft: (
    /** @type {string} */ draftId,
    /** @type {ClassificationStandardActionPayload} */ payload,
  ) =>
    request(`/api/classification-standard-drafts/${draftId}/publish`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  /** @returns {Promise<ClassificationStandardDiscardResult>} */
  discardClassificationStandardDraft: (
    /** @type {string} */ draftId,
    /** @type {ClassificationStandardActionPayload} */ payload,
  ) =>
    request(`/api/classification-standard-drafts/${draftId}/discard`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  /** @returns {Promise<ClassificationStandardValidationSource[]>} */
  classificationStandardValidationSources: (/** @type {string} */ draftId) =>
    request(`/api/classification-standard-drafts/${draftId}/validation-sources`),
  /** @returns {Promise<ClassificationStandardValidationRunSummary[]>} */
  classificationStandardValidationRuns: (/** @type {string} */ draftId) =>
    request(`/api/classification-standard-drafts/${draftId}/validation-runs`),
  /** @returns {Promise<ClassificationStandardValidationRunDetail>} */
  createClassificationStandardValidationRun: (
    /** @type {string} */ draftId,
    /** @type {ClassificationStandardValidationRunPayload} */ payload,
  ) =>
    request(`/api/classification-standard-drafts/${draftId}/validation-runs`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  /** @returns {Promise<ClassificationStandardValidationRunDetail>} */
  createReviewStandardValidationRun: (
    /** @type {string} */ draftId,
    /** @type {File} */ file,
    /** @type {number} */ revision,
    /** @type {ValidationSampleSize} */ sampleSize,
    /** @type {ValidationComparisonType} */ comparisonType = "standard_version",
  ) => {
    const body = new FormData();
    body.append("file", file);
    body.append("expected_revision", String(revision));
    body.append("sample_size", String(sampleSize));
    body.append("comparison_type", comparisonType);
    return request(
      `/api/classification-standard-drafts/${draftId}/review-validation-runs`,
      {
        method: "POST",
        body,
      },
    );
  },
  /** @returns {Promise<ClassificationStandardValidationRunDetail>} */
  classificationStandardValidationRun: (/** @type {string} */ runId) =>
    request(`/api/classification-standard-validation-runs/${runId}`),
  /** @returns {Promise<ClassificationStandardValidationRunDetail>} */
  approveClassificationStandardValidationRun: (
    /** @type {string} */ runId,
    /** @type {ClassificationStandardValidationApprovalPayload} */ payload,
  ) =>
    request(`/api/classification-standard-validation-runs/${runId}/approve`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  /** @returns {Promise<ClassificationResultTaxonomy>} */
  resultTaxonomy: (
    /** @type {string} */ resultVersionId,
    /** @type {RequestInit} */ options = {},
  ) => request(`/api/classification-results/${resultVersionId}/taxonomy`, options),
};
