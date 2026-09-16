const STORAGE_PREFIX = "seekway.task-create.draft.v1";

/** @typedef {import("./taskCreateContracts").TaskDraft} TaskDraft */

/** @param {string} userId */
function storageKey(userId) {
  return userId ? `${STORAGE_PREFIX}.${encodeURIComponent(userId)}` : null;
}

/** @param {string} userId @returns {TaskDraft | null} */
export function readTaskDraft(userId) {
  const key = storageKey(userId);
  if (!key) return null;
  try {
    return JSON.parse(window.sessionStorage.getItem(key) || "null");
  } catch {
    return null;
  }
}

/** @param {string} userId @param {TaskDraft} draft */
export function writeTaskDraft(userId, draft) {
  const key = storageKey(userId);
  if (!key) return;
  window.sessionStorage.setItem(key, JSON.stringify(draft));
}

/** @param {string} userId @param {Partial<TaskDraft>} changes */
export function updateTaskDraft(userId, changes) {
  const current = readTaskDraft(userId) ?? {};
  const next = { ...current, ...changes };
  writeTaskDraft(userId, next);
  return next;
}

/** @param {string} userId */
export function clearTaskDraft(userId) {
  const key = storageKey(userId);
  if (key) window.sessionStorage.removeItem(key);
}
