const STORAGE_PREFIX = "seekway.task-create.draft.v1";

function storageKey(userId) {
  return userId ? `${STORAGE_PREFIX}.${encodeURIComponent(userId)}` : null;
}

export function readTaskDraft(userId) {
  const key = storageKey(userId);
  if (!key) return null;
  try {
    return JSON.parse(window.sessionStorage.getItem(key) || "null");
  } catch {
    return null;
  }
}

export function writeTaskDraft(userId, draft) {
  const key = storageKey(userId);
  if (!key) return;
  window.sessionStorage.setItem(key, JSON.stringify(draft));
}

export function updateTaskDraft(userId, changes) {
  const current = readTaskDraft(userId) ?? {};
  const next = { ...current, ...changes };
  writeTaskDraft(userId, next);
  return next;
}

export function clearTaskDraft(userId) {
  const key = storageKey(userId);
  if (key) window.sessionStorage.removeItem(key);
}
