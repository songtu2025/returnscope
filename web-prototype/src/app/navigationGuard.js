export const NAVIGATION_REQUEST_EVENT = "app:navigation-request";
const HISTORY_INDEX = "seekwayNavigationIndex";

/** @param {() => void} proceed */
export function requestNavigation(proceed) {
  const event = new CustomEvent(NAVIGATION_REQUEST_EVENT, {
    cancelable: true,
    detail: { proceed },
  });
  return window.dispatchEvent(event);
}

export function historyIndex() {
  const index = window.history.state?.[HISTORY_INDEX];
  return typeof index === "number" ? index : null;
}

/** @param {string} hash @param {number} index @param {boolean} replace */
export function writeHistory(hash, index, replace) {
  const state = { ...window.history.state, [HISTORY_INDEX]: index };
  const url = `${window.location.pathname}${window.location.search}${hash}`;
  if (replace) window.history.replaceState(state, "", url);
  else window.history.pushState(state, "", url);
}
