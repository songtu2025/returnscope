import { useCallback, useEffect, useState } from "react";

import { LEGACY_ROUTES, PAGE_IDS, routeForDestination } from "./navigation";

/** @typedef {import("./navigation").AppRoute} AppRoute */
/** @typedef {import("./navigation").NavigationFocus} NavigationFocus */
/** @typedef {import("./navigation").RouteQuery} RouteQuery */

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
  window.history.replaceState(
    null,
    "",
    `${window.location.pathname}${window.location.search}${hash}`,
  );
}

/**
 * @param {string} page
 * @param {Record<string, string | number | boolean | null | undefined>} [query]
 * @param {{replace?: boolean}} [options]
 */
export function navigateHash(page, query = {}, { replace = false } = {}) {
  const hash = buildHash(page, query);
  if (replace) {
    replaceHash(hash);
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    return;
  }
  window.location.hash = hash;
}

export function useHashRoute() {
  const [route, setRoute] = useState(() => parseHash());

  useEffect(() => {
    const sync = () => {
      const next = parseHash();
      if (next.isLegacy && window.location.hash !== next.canonicalHash) {
        replaceHash(next.canonicalHash);
      }
      setRoute(next);
    };
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  const navigate = useCallback(
    /**
     * @param {string} destination
     * @param {NavigationFocus | null} [focus]
     */
    (destination, focus = null) => {
      const target = routeForDestination(destination, focus);
      navigateHash(target.page, target.query);
      window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    },
    [],
  );

  return { route, navigate };
}
