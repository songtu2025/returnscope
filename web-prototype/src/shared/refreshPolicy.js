export const DATA_CHANGED_EVENT = "seekway:data-changed";
export const REFRESH_INTERVALS = {
  ordinary: 60000,
  activeTask: 10000,
  activeJob: 2000,
};

// 自动触发统一交给刷新 Hook，SWR 继续负责缓存和同键请求共享。
export const MANAGED_REFRESH_OPTIONS = {
  revalidateOnFocus: false,
  revalidateOnReconnect: false,
  refreshInterval: 0,
};

/** @param {string[]} domains */
export function notifyDataChanged(domains) {
  window.dispatchEvent(new CustomEvent(DATA_CHANGED_EVENT, { detail: domains }));
}
