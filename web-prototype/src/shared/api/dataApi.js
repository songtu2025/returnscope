import { API_BASE, queryString, request } from "./request";

export const dataApi = {
  mysqlReturnSchema: ({ refresh = false, ...options } = {}) =>
    request(
      `/api/mysql-return-imports/schema${refresh ? "?refresh=true" : ""}`,
      options,
    ),
  previewMysqlReturns: (payload, options = {}) =>
    request("/api/mysql-return-imports/preview", {
      ...options,
      method: "POST",
      body: JSON.stringify(payload),
    }),
  importMysqlReturns: (payload) =>
    request("/api/mysql-return-imports", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  importRules: (options = {}) => request("/api/import-rules", options),
  datasets: (kind = "", options = {}) =>
    request(`/api/datasets${kind ? `?kind=${kind}` : ""}`, options),
  managedDatasets: (kind = "returns", options = {}) =>
    request(`/api/datasets${queryString({ kind, usage_scope: "managed" })}`, options),
  dataVersions: (kind = "", options = {}) =>
    request(`/api/data-versions${kind ? `?kind=${kind}` : ""}`, options),
  dataVersionReferences: (versionId, filters = {}, options = {}) =>
    request(
      `/api/data-versions/${versionId}/references${queryString(filters)}`,
      options,
    ),
  qualityPreflight: (returnsVersionId, productsVersionId, options = {}) =>
    request(
      `/api/data-quality/preflight${queryString({
        returns_version_id: returnsVersionId,
        products_version_id: productsVersionId,
      })}`,
      options,
    ),
  qualityIssues: (filters = {}, options = {}) =>
    request(`/api/data-quality/issues${queryString(filters)}`, options),
  productScopes: (versionId) => request(`/api/data-versions/${versionId}/scopes`),
  dataset: (id, { include = "", ...options } = {}) =>
    request(`/api/datasets/${id}${queryString({ include })}`, options),
  datasetStorageSummary: (datasetIds, filters = {}, options = {}) =>
    request(
      `/api/dataset-storage${queryString({
        dataset_ids: datasetIds.join(","),
        retention_days: 30,
        retain_latest: 2,
        ...filters,
      })}`,
      options,
    ),
  cleanupDatasetStorage: (payload) =>
    request("/api/dataset-storage/cleanup", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  datasetDownloadUrl: (id, version = "") =>
    `${API_BASE}/api/datasets/${id}/download${version ? `?version=${version}` : ""}`,
  datasetRows: (id, query = "", offset = 0, limit = 15, filters = {}, options = {}) =>
    request(
      `/api/datasets/${id}/rows${queryString({
        q: query,
        offset,
        limit,
        ...filters,
      })}`,
      options,
    ),
  updateDatasetRow: (id, payload) =>
    request(`/api/datasets/${id}/rows`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  completeProductCategories: (id, payload) =>
    request(`/api/datasets/${id}/category-completion`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  createDataset: (formData) =>
    request("/api/datasets", { method: "POST", body: formData }),
  addDatasetVersion: (id, formData) =>
    request(`/api/datasets/${id}/versions`, { method: "POST", body: formData }),
  inspectReturnImport: (formData) =>
    request("/api/return-imports/inspect", { method: "POST", body: formData }),
  importReturns: (payload) =>
    request("/api/return-imports", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
