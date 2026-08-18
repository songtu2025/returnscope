const STORAGE_PREFIX = "seekway:dashboard-selection";

function storageKey(userId, token) {
  return `${STORAGE_PREFIX}:${userId || "anonymous"}:${token}`;
}

function randomToken() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export function createDashboardSelection(userId, initial = {}) {
  const token = randomToken();
  writeDashboardSelection(userId, token, {
    selected: [],
    resolved_result_version_ids: [],
    ...initial,
  });
  return token;
}

export function readDashboardSelection(userId, token) {
  if (!token) return null;
  try {
    const value = JSON.parse(
      sessionStorage.getItem(storageKey(userId, token)) || "null",
    );
    if (!value || !Array.isArray(value.selected)) return null;
    return value;
  } catch {
    return null;
  }
}

export function writeDashboardSelection(userId, token, value) {
  if (!token) return;
  sessionStorage.setItem(
    storageKey(userId, token),
    JSON.stringify({ ...value, updated_at: new Date().toISOString() }),
  );
}

export function updateDashboardSelection(userId, token, updater) {
  const current = readDashboardSelection(userId, token) ?? { selected: [] };
  const next = updater(current);
  writeDashboardSelection(userId, token, next);
  return next;
}

export function clearDashboardSelection(userId, token) {
  if (token) sessionStorage.removeItem(storageKey(userId, token));
}

export function resultVersionId(result) {
  return result.version_id || result.result_version_id || result.id;
}

export function selectionItem(result) {
  return {
    result_version_id: resultVersionId(result),
    result_version_no: result.version,
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
