export const serverStateConfig = {
  provider: () => new Map(),
  revalidateOnFocus: true,
  shouldRetryOnError: false,
};

export const serverStateKeys = {
  /** @param {number} limit */
  workbenchSummary: (limit) => ["workbench", "summary", limit],
  taskList: ["analysis-tasks", "list", { include_archived: true }],
  productDatasets: ["data-assets", "products", "list"],
  /** @param {string} datasetId @param {string} include */
  productDataset: (datasetId, include) => [
    "data-assets",
    "products",
    "detail",
    datasetId,
    include,
  ],
  returnSources: ["data-assets", "returns", "list"],
  /** @param {string} sourceId @param {string[]} memberIds */
  returnSourceDetails: (sourceId, memberIds) => [
    "data-assets",
    "returns",
    "detail",
    sourceId,
    memberIds,
  ],
  taskCreateSetup: ["task-create", "setup"],
  mysqlReturnSchema: ["task-create", "mysql-return-schema"],
  /** @param {string} taskId */
  taskTemplate: (taskId) => ["task-create", "template", taskId],
  /** @param {Record<string, string | number | null | undefined>} query */
  classificationResultList: (query) => ["classification-results", "list", query],
  /** @param {string} versionId */
  classificationResultOverview: (versionId) => [
    "classification-results",
    "overview",
    versionId,
  ],
  /** @param {string} versionId @param {Record<string, string | number>} query */
  classificationResultRecords: (versionId, query) => [
    "classification-results",
    "records",
    versionId,
    query,
  ],
  /** @param {Record<string, string | number>} query */
  dashboardList: (query) => ["analysis-dashboards", "list", query],
};
