import { useCallback, useEffect, useRef, useState } from "react";

import { LEGACY_ROUTES, PAGE_IDS, routeForDestination } from "./navigation";
import { historyIndex, requestNavigation, writeHistory } from "./navigationGuard";

/** @typedef {import("./navigation").AppRoute} AppRoute */
/** @typedef {import("./navigation").NavigationFocus} NavigationFocus */
/** @typedef {import("./navigation").RouteQuery} RouteQuery */

const ROUTE_CHANGE_EVENT = "app:routechange";

/** @param {URLSearchParams} params */
function queryObject(params) {
  return Object.fromEntries(params.entries());
}

/**
 * @param {string} page
 * @param {Record<string, string | number | boolean | null | undefined>} [query]
 */
export function buildHash(page, query = {}) {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== undefined) {
      params.set(key, String(value));
    }
  });
  const suffix = params.toString();
  return `#${page}${suffix ? `?${suffix}` : ""}`;
}

/**
 * @param {string} [hash]
 * @returns {AppRoute & {isLegacy: boolean, canonicalHash: string}}
 */
export function parseHash(hash = window.location.hash) {
  const source = hash.replace(/^#/, "");
  const [rawPage = "", rawQuery = ""] = source.split("?");
  const legacy = LEGACY_ROUTES[rawPage];
  const page = legacy?.page ?? (PAGE_IDS.has(rawPage) ? rawPage : "workbench");
  const query = {
    ...(legacy?.query ?? {}),
    ...queryObject(new URLSearchParams(rawQuery)),
  };
  return {
    page,
    query,
    isLegacy: Boolean(legacy) || !PAGE_IDS.has(rawPage),
    canonicalHash: buildHash(page, query),
  };
}

/** @param {string} hash */
function replaceHash(hash) {
  writeHistory(hash, historyIndex() ?? 0, true);
}

function notifyRouteChange() {
  window.dispatchEvent(new Event(ROUTE_CHANGE_EVENT));
}

/**
 * @param {string} page
 * @param {Record<string, string | number | boolean | null | undefined>} [query]
 * @param {{replace?: boolean}} [options]
 */
export function navigateHash(page, query = {}, { replace = false } = {}) {
  const hash = buildHash(page, query);
  if (hash === window.location.hash) return true;
  const proceed = () => {
    const index = historyIndex() ?? 0;
    if (historyIndex() === null) writeHistory(window.location.hash, index, true);
    writeHistory(hash, index + (replace ? 0 : 1), replace);
    notifyRouteChange();
  };
  if (!requestNavigation(proceed)) return false;
  proceed();
  return true;
}

export function useHashRoute() {
  const [route, setRoute] = useState(() => parseHash());
  const current = useRef({ route, index: historyIndex() ?? 0 });

  useEffect(() => {
    let restoring = false;
    let approvedHash = "";
    let afterRestore = /** @type {(() => void) | null} */ (null);
    if (historyIndex() === null) replaceHash(window.location.hash);
    const sync = (/** @type {Event | undefined} */ event) => {
      const next = parseHash();
      const nextIndex = historyIndex() ?? current.current.index + 1;
      if (restoring) {
        if (nextIndex !== current.current.index) return;
        restoring = false;
        afterRestore?.();
        afterRestore = null;
        return;
      }
      if (next.canonicalHash === current.current.route.canonicalHash) {
        if (next.isLegacy && window.location.hash !== next.canonicalHash) {
          replaceHash(next.canonicalHash);
        }
        current.current.index = nextIndex;
        return;
      }
      if (
        event &&
        event.type !== ROUTE_CHANGE_EVENT &&
        approvedHash !== next.canonicalHash
      ) {
        const delta = nextIndex - current.current.index;
        const proceed = () => {
          const traverse = () => {
            approvedHash = next.canonicalHash;
            window.history.go(delta);
          };
          if (restoring) afterRestore = traverse;
          else traverse();
        };
        if (!requestNavigation(proceed)) {
          // 浏览器已移动历史游标，先返回原记录；确认后再沿原方向前进，保留历史链。
          restoring = true;
          window.history.go(-delta);
          return;
        }
      }
      approvedHash = "";
      if (next.isLegacy && window.location.hash !== next.canonicalHash) {
        replaceHash(next.canonicalHash);
      }
      current.current = { route: next, index: nextIndex };
      if (historyIndex() === null) writeHistory(next.canonicalHash, nextIndex, true);
      setRoute((current) =>
        current.canonicalHash === next.canonicalHash ? current : next,
      );
    };
    sync(undefined);
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    window.addEventListener(ROUTE_CHANGE_EVENT, sync);
    return () => {
      window.removeEventListener("hashchange", sync);
      window.removeEventListener("popstate", sync);
      window.removeEventListener(ROUTE_CHANGE_EVENT, sync);
    };
  }, []);

  const navigate = useCallback(
    /**
     * @param {string} destination
     * @param {NavigationFocus | null} [focus]
     */
    (destination, focus = null) => {
      const target = routeForDestination(destination, focus);
      if (navigateHash(target.page, target.query)) {
        window.scrollTo({ top: 0, left: 0, behavior: "auto" });
      }
    },
    [],
  );

  return { route, navigate };
}
