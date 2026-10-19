import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { taskApi } from "../../shared/api/taskApi";
import { refreshServerState } from "../../shared/serverState";
import { MANAGED_REFRESH_OPTIONS } from "../../shared/refreshPolicy";

/** @param {{search: string, page: number, pageSize: number, setPage: (page: number) => void}} options */
export function useTaskRecycleData({ search, page, pageSize, setPage }) {
  const { mutate: mutateCache } = useSWRConfig();
  const [refreshError, setRefreshError] = useState(false);
  const readRecycle = async () =>
    /** @type {{items: import("./taskRecycleContracts").RecycledListing[], total: number}} */ (
      await taskApi.recycledListings({ q: search, page, page_size: pageSize })
    );
  const { data, error, mutate } = useSWR(
    ["task-recycle", search, page, pageSize],
    readRecycle,
    MANAGED_REFRESH_OPTIONS,
  );
  const {
    data: totalData,
    error: totalError,
    mutate: refreshTotal,
  } = useSWR(
    search ? ["task-recycle-total"] : null,
    async () =>
      /** @type {{total: number}} */ (
        await taskApi.recycledListings({ page: 1, page_size: 1 })
      ),
    MANAGED_REFRESH_OPTIONS,
  );
  const refresh = async () => {
    const next = await mutate(readRecycle, { revalidate: false });
    if (search) await refreshTotal();
    if (next && page > Math.max(1, Math.ceil(next.total / pageSize)))
      setPage(Math.max(1, Math.ceil(next.total / pageSize)));
  };
  const refreshAfterAction = async () => {
    setRefreshError(false);
    const reads = await Promise.allSettled([
      refreshServerState(mutateCache, ["analysis-tasks", "workbench", "data-assets"]),
      refresh(),
    ]);
    setRefreshError(reads.some((read) => read.status === "rejected"));
  };
  /** @param {string[]} ids */
  const removeItems = async (ids) => {
    await mutate(
      (current) => {
        if (!current) return current;
        const items = current.items.filter((item) => !ids.includes(item.id));
        return {
          ...current,
          items,
          total: Math.max(0, current.total - current.items.length + items.length),
        };
      },
      { revalidate: false },
    );
  };
  return {
    data,
    error,
    totalData,
    totalError,
    refreshError,
    refresh,
    refreshAfterAction,
    removeItems,
  };
}
