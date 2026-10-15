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

/** 按任务 ID 更新已访问页面的名称，避免切回页面时先显示旧缓存。
 * @param {import("swr").ScopedMutator} mutate
 * @param {import("../features/task-runtime/taskRuntimeContracts").AnalysisTask} task
 * @param {string} previousTitle
 */
export async function refreshTaskNameState(mutate, task, previousTitle) {
  await Promise.all([
    mutate(
      (key) => Array.isArray(key) && key[0] === "analysis-tasks" && key[1] === "list",
      (
        /** @type {import("../features/task-runtime/taskRuntimeContracts").AnalysisTask[] | undefined} */ current,
      ) =>
        current?.map((item) =>
          item.id === task.id ? { ...item, title: task.title } : item,
        ),
      { revalidate: false },
    ),
    mutate(
      (key) => Array.isArray(key) && key[0] === "workbench",
      (
        /** @type {import("./api/workbenchContracts").WorkbenchSummary | undefined} */ current,
      ) =>
        current && {
          ...current,
          actions: current.actions.map((action) => {
            if (action.target.task_id !== task.id) return action;
            if (action.object_type === "task") return { ...action, title: task.title };
            if (
              action.object_type === "task_segment" &&
              action.title.startsWith(`${previousTitle} / `)
            )
              return {
                ...action,
                title: task.title + action.title.slice(previousTitle.length),
              };
            return action;
          }),
        },
      { revalidate: false },
    ),
    mutate(
      (key) =>
        Array.isArray(key) && key[0] === "data-assets" && key[1] === "references",
      (
        /** @type {import("./api/dataManagementContracts").DatasetReferencePage | undefined} */ current,
      ) =>
        current && {
          ...current,
          items: current.items.map((item) =>
            item.task_id === task.id ? { ...item, title: task.title } : item,
          ),
        },
      { revalidate: false },
    ),
  ]);
  return refreshServerState(mutate, ["workbench", "data-assets"]);
}

export const serverStateKeys = {
  /** @param {number} limit */
  workbenchSummary: (limit) => ["workbench", "summary", limit],
  /** @param {string} [ownerId] @returns {[string, string, Record<string, string | boolean>]} */
  taskList: (ownerId) => [
    "analysis-tasks",
    "list",
    { include_archived: true, ...(ownerId === undefined ? {} : { owner_id: ownerId }) },
  ],
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
