export const serverStateConfig = {
  provider: () => new Map(),
  revalidateOnFocus: true,
  shouldRetryOnError: false,
};

export const serverStateKeys = {
  /** @param {number} limit */
  workbenchSummary: (limit) => ["workbench", "summary", limit],
  taskList: ["analysis-tasks", "list", { include_archived: true }],
  /** @param {Record<string, string | number>} query */
  dashboardList: (query) => ["analysis-dashboards", "list", query],
};
