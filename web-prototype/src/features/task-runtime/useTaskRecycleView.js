import { useEffect, useState } from "react";
import { buildHash, navigateHash } from "../../app/hashRouter";

/** @param {Record<string, string | undefined>} query */
export function recycleViewState(query) {
  const page = Number(query.page);
  const size = Number(query.page_size);
  return {
    search: query.q || "",
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
    pageSize: [20, 50, 100].includes(size) ? size : 20,
  };
}
/** @param {{search: string, page: number, pageSize: number}} state */
export const recycleViewQuery = (state) => ({
  view: "recycle",
  q: state.search,
  page: state.page === 1 ? "" : state.page,
  page_size: state.pageSize === 20 ? "" : state.pageSize,
});

/** @param {Record<string, string | undefined> | undefined} routeQuery */
export function useTaskRecycleView(routeQuery) {
  const [local, setLocal] = useState(() => recycleViewState(routeQuery ?? {}));
  const state = routeQuery ? recycleViewState(routeQuery) : local;
  const [query, setQuery] = useState(state.search);
  useEffect(() => {
    setQuery(state.search);
  }, [state.search]);
  /** @param {Partial<typeof state>} changes */
  const update = (changes) => {
    const next = { ...state, ...changes };
    if (routeQuery)
      navigateHash("analysis-tasks", recycleViewQuery(next), { replace: true });
    else setLocal(next);
  };
  return {
    ...state,
    query,
    setQuery,
    update,
    returnHash: buildHash("analysis-tasks", recycleViewQuery(state)),
  };
}
