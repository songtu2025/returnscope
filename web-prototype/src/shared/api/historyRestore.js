import { request } from "./request";

/** @typedef {{id: string, created_at: string, actor_name: string, before: {semantic_units?: {label_code: string, opinion?: string}[]}}} SemanticChange */
/** @param {string} versionId @param {string} recordId @returns {Promise<SemanticChange[]>} */
export function semanticChanges(versionId, recordId) {
  return request(
    `/api/classification-results/${versionId}/records/${recordId}/corrections`,
  );
}
/** @param {string} versionId @param {string} recordId @param {string} auditId @returns {Promise<{version_id: string}>} */
export function restoreSemanticChange(versionId, recordId, auditId) {
  return request(
    `/api/classification-results/${versionId}/records/${recordId}/restore-semantics`,
    { method: "POST", body: JSON.stringify({ audit_id: auditId }) },
  );
}

/** @param {string} datasetId @param {string} auditId @param {number} version @returns {Promise<import("./dataManagementContracts").DatasetRecord>} */
export function restoreProductChange(datasetId, auditId, version) {
  return request(`/api/datasets/${datasetId}/changes/${auditId}/restore`, {
    method: "POST",
    body: JSON.stringify({ expected_version: version }),
  });
}
