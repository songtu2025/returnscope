import { useEffect, useEffectEvent } from "react";
import { DATA_CHANGED_EVENT, REFRESH_INTERVALS } from "../shared/refreshPolicy";

/** 合并焦点、可见性、联网、业务变更和轮询触发；错误交由业务数据状态展示。
 * @param {() => unknown | Promise<unknown>} refresh
 * @param {{interval?: number, enabled?: boolean, loading?: boolean, domains?: string[], identity?: string}} [options]
 */
export function useDataRefresh(
  refresh,
  {
    interval = REFRESH_INTERVALS.ordinary,
    enabled = true,
    loading = false,
    domains = [],
    identity = "",
  } = {},
) {
  const domainKey = domains.join(",");
  const read = useEffectEvent(() => refresh());
  const busy = useEffectEvent(() => loading);
  useEffect(() => {
    if (!enabled) return undefined;
    let disposed = false;
    let running = false;
    let invalidated = false;
    let timer = 0;
    let lastStarted = -Infinity;
    const visible = () => !document.hidden && navigator.onLine !== false;
    const run = async () => {
      timer = 0;
      if (disposed || !visible() || running) return;
      if (busy()) {
        if (invalidated) timer = window.setTimeout(run, 250);
        return;
      }
      running = true;
      invalidated = false;
      lastStarted = Date.now();
      try {
        await read();
      } catch {
        // SWR 或业务 Hook 已保留错误及上次数据，下一次正常触发可以恢复。
      } finally {
        running = false;
        if (!disposed && invalidated) timer = window.setTimeout(run, 250);
      }
    };
    const request = (changed = false) => {
      if (changed) invalidated = true;
      if (disposed || !visible() || running || timer) return;
      if (!changed && Date.now() - lastStarted < 1000) return;
      timer = window.setTimeout(run, 100);
    };
    const onResume = () => request();
    const onChanged = (/** @type {Event} */ event) => {
      const changed = /** @type {CustomEvent<string[]>} */ (event).detail;
      if (changed.some((domain) => domainKey.split(",").includes(domain)))
        request(true);
    };
    const intervalTimer = interval ? window.setInterval(onResume, interval) : null;
    window.addEventListener("focus", onResume);
    window.addEventListener("online", onResume);
    document.addEventListener("visibilitychange", onResume);
    window.addEventListener(DATA_CHANGED_EVENT, onChanged);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      if (intervalTimer !== null) window.clearInterval(intervalTimer);
      window.removeEventListener("focus", onResume);
      window.removeEventListener("online", onResume);
      document.removeEventListener("visibilitychange", onResume);
      window.removeEventListener(DATA_CHANGED_EVENT, onChanged);
    };
  }, [domainKey, enabled, identity, interval]);
}
