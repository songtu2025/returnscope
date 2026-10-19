const STORAGE_PREFIX = "seekway:dashboard-selection";

/** @typedef {import("./analysisDashboardContracts").DashboardSelection} DashboardSelection */
/** @typedef {import("./analysisDashboardContracts").DashboardSelectionItem} DashboardSelectionItem */
/** @typedef {import("./analysisDashboardContracts").DashboardSelectionSource} DashboardSelectionSource */

/** @param {string} userId @param {string} token */
function storageKey(userId, token) {
  return `${STORAGE_PREFIX}:${userId || "anonymous"}:${token}`;
}

function randomToken() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

/** @param {string} userId @param {Partial<DashboardSelection>} [initial] */
export function createDashboardSelection(userId, initial = {}) {
  const token = randomToken();
  writeDashboardSelection(userId, token, {
    selected: [],
    resolved_result_version_ids: [],
    ...initial,
  });
  return token;
}

/** @param {string} userId @param {string} token @returns {DashboardSelection | null} */
export function readDashboardSelection(userId, token) {
  if (!token) return null;
  try {
    const value = JSON.parse(
      sessionStorage.getItem(storageKey(userId, token)) || "null",
    );
    if (!value || !Array.isArray(value.selected)) return null;
    // 仅恢复当前选择流程的数据，旧会话的目标看板和版本原因不再驱动操作。
    return /** @type {DashboardSelection} */ ({
      selected: value.selected,
      resolved_result_version_ids: value.resolved_result_version_ids,
      filters: value.filters,
      intent: value.intent,
      result_pool_query: value.result_pool_query,
      task_return: value.task_return,
      result_return: value.result_return,
      dashboard_form: value.dashboard_form
        ? { name: value.dashboard_form.name || "" }
        : undefined,
      insight_form: value.insight_form,
      updated_at: value.updated_at,
    });
  } catch {
    return null;
  }
}

/** @param {string} userId @param {string} token @param {DashboardSelection} value */
function writeDashboardSelection(userId, token, value) {
  if (!token) return;
  sessionStorage.setItem(
    storageKey(userId, token),
    JSON.stringify({ ...value, updated_at: new Date().toISOString() }),
  );
}

/** @param {string} userId @param {string} token @param {(selection: DashboardSelection) => DashboardSelection} updater */
export function updateDashboardSelection(userId, token, updater) {
  const current = readDashboardSelection(userId, token) ?? {
    selected: [],
    resolved_result_version_ids: [],
  };
  const next = updater(current);
  writeDashboardSelection(userId, token, next);
  return next;
}

/** @param {string} userId @param {string} token */
export function clearDashboardSelection(userId, token) {
  if (token) sessionStorage.removeItem(storageKey(userId, token));
}

/** @param {DashboardSelectionSource} result */
function resultVersionId(result) {
  return result.version_id || result.result_version_id || result.id || "";
}

/** @param {DashboardSelectionSource} result @returns {DashboardSelectionItem} */
export function selectionItem(result) {
  return {
    result_version_id: resultVersionId(result),
    result_version_no: Number(result.version || 0),
    store_site: result.store_site || "",
    listing: result.listing || "",
    quality_status: result.quality_status || "",
    record_count: Number(result.record_count || 0),
    unit_count: Number(result.unit_count || 0),
    product_names: Array.isArray(result.product_names)
      ? result.product_names.filter(Boolean)
      : result.product_name
        ? [result.product_name]
        : [],
    published_at: result.published_at || result.created_at || "",
  };
}
