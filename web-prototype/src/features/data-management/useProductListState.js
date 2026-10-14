import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { navigateHash, useHashRoute } from "../../app/hashRouter";

/** 产品列表条件写入现有路由，切换页签及浏览器返回时恢复。 */
export function useProductListState() {
  const { route } = useHashRoute();
  const routeRef = useRef(route);
  useLayoutEffect(() => {
    routeRef.current = route;
  }, [route]);
  const routed = route.page === "data-assets";
  const [local, setLocal] = useState({ query: "", store: "", category: "", page: 1 });
  const state = routed
    ? {
        query: route.query.rows_q || "",
        store: route.query.rows_store || "",
        category: route.query.rows_category || "",
        page: Math.max(1, Number(route.query.rows_page) || 1),
      }
    : local;
  const [draftQuery, setDraftQuery] = useState(state.query);
  useEffect(() => setDraftQuery(state.query), [state.query]);
  /** @param {Partial<typeof local>} changes */
  const change = (changes) => {
    if (!routed) {
      setLocal((current) => ({ ...current, ...changes }));
      return;
    }
    const query = { ...routeRef.current.query };
    for (const [key, value] of Object.entries(changes)) {
      query[`rows_${key === "query" ? "q" : key}`] = String(value);
    }
    routeRef.current = { ...routeRef.current, query };
    navigateHash("data-assets", query, { replace: true });
  };
  return {
    ...state,
    draftQuery,
    setDraftQuery,
    setQuery: (/** @type {string} */ query) => change({ query, page: 1 }),
    setStore: (/** @type {string} */ store) => change({ store, page: 1 }),
    setCategory: (/** @type {string} */ category) => change({ category, page: 1 }),
    setPage: (/** @type {import("react").SetStateAction<number>} */ page) =>
      change({ page: typeof page === "function" ? page(state.page) : page }),
  };
}
