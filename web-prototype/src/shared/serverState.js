import { notifyDataChanged } from "./refreshPolicy";
export const serverStateConfig = {
  provider: () => new Map(),
  revalidateOnFocus: true,
  shouldRetryOnError: false,
};

/** @param {import("swr").ScopedMutator} mutate */
export function refreshProductState(mutate) {
  return refreshServerState(mutate, [
    "data-assets",
    "classification-results",
    "analysis-dashboards",
    "task-create",
    "workbench",
    "analysis-tasks",
  ]);
}

/** 保存后统一通知关联模块；后台更新保留现有缓存，避免短暂清空。
 * @param {import("swr").ScopedMutator} mutate
 * @param {string[]} domains
 */
export function refreshServerState(mutate, domains) {
  notifyDataChanged(domains);
  return mutate((key) => Array.isArray(key) && domains.includes(key[0]));
}

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
