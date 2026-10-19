import "./taskRecycle.css";
import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { useDataRefresh } from "../../hooks/useDataRefresh";
import { refreshServerState } from "../../shared/serverState";
import { ArrowLeft } from "@phosphor-icons/react";
import { taskApi } from "../../shared/api/taskApi";
import { errorMessage } from "../../shared/api/requestErrors";
import { PageHeading, PageLoadingState } from "../../components/SharedUi";
import { TaskRecycleRowActions } from "./TaskRecycleRowActions";
import { TaskRecyclePurgeDialog } from "./TaskRecycleDialogs";
import { TaskRecycleToolbar } from "./TaskRecycleToolbar";
import { Pagination } from "../../components/Pagination";
import { formatTime } from "../../lib/presentation";
import { MANAGED_REFRESH_OPTIONS } from "../../shared/refreshPolicy";
import { navigateHash } from "../../app/hashRouter";

/** @typedef {{id: string, task_id: string, segment_key: string, task_title: string, task_revision: number, removed_by: string, deleted_at: string, scope: {listing?: string, store?: string}}} RecycledListing */
/** @param {{notify: (message: string, type?: "success" | "error") => void}} props */
export function TaskRecyclePage({ notify }) {
  const { mutate: mutateCache } = useSWRConfig();
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [busy, setBusy] = useState("");
  const [restored, setRestored] = useState(
    /** @type {RecycledListing | null} */ (null),
  );
  const [refreshError, setRefreshError] = useState(false);
  const [purging, setPurging] = useState(/** @type {RecycledListing | null} */ (null));
  const readRecycle = async () =>
    /** @type {{items: RecycledListing[], total: number}} */ (
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
    const results = await Promise.allSettled([
      refreshServerState(mutateCache, ["analysis-tasks", "workbench", "data-assets"]),
      refresh(),
    ]);
    setRefreshError(results.some((result) => result.status === "rejected"));
  };
  useDataRefresh(refresh, {
    domains: ["task-recycle"],
    loading: Boolean(busy),
    identity: `${search}:${page}:${pageSize}`,
  });
  const applySearch = (/** @type {string} */ value) => {
    setQuery(value);
    setSearch(value);
    setPage(1);
  };
  const pagination = {
    page,
    pageSize,
    total: data?.total ?? 0,
    totalPages: Math.max(1, Math.ceil((data?.total ?? 0) / pageSize)),
    disabled: Boolean(busy) || !data,
    onPage: setPage,
    onPageSize: (/** @type {number} */ size) => {
      setPageSize(size);
      setPage(1);
    },
    showQuickJumper: true,
  };
  /** @param {RecycledListing} item @param {"restore" | "purge"} action */
  const act = async (item, action) => {
    setBusy(item.id);
    try {
      try {
        await taskApi.controlTaskSegment(item.task_id, item.segment_key, action, {
          expected_revision: item.task_revision,
        });
      } catch (failure) {
        notify(errorMessage(failure), "error");
        await refreshAfterAction();
        return;
      }
      setPurging(null);
      if (action === "restore") setRestored(item);
      notify(
        action === "restore"
          ? "Listing 已恢复，不会自动执行"
          : "Listing 已永久删除，已有产出保留",
      );
      await mutate(
        (current) =>
          current && {
            ...current,
            items: current.items.filter((row) => row.id !== item.id),
            total: Math.max(0, current.total - 1),
          },
        { revalidate: false },
      );
      await refreshAfterAction();
    } finally {
      setBusy("");
    }
  };
  return (
    <div className="standard-page task-page task-runtime-workspace">
      <button
        className="task-back-button"
        onClick={() => navigateHash("analysis-tasks")}
      >
        <ArrowLeft size={17} />
        全部任务
      </button>
      <PageHeading title="Listing 回收站" />
      {restored && (
        <div className="recycle-restore-result" role="status" aria-label="恢复结果">
          <span>{restored.scope.listing || "Listing"} 已恢复，不会自动执行</span>
          <button
            className="text-button"
            onClick={() =>
              navigateHash("analysis-tasks", {
                task_id: restored.task_id,
                segment_id: restored.id,
              })
            }
          >
            查看所属任务
          </button>
        </div>
      )}
      {refreshError && (
        <div role="alert">
          列表刷新失败，已确认的操作结果保留。
          <button
            className="text-button"
            disabled={Boolean(busy)}
            onClick={refreshAfterAction}
          >
            重试刷新
          </button>
        </div>
      )}
      <TaskRecycleToolbar
        query={query}
        search={search}
        total={search ? totalData?.total : data?.total}
        countError={Boolean(totalError)}
        matches={data?.total ?? 0}
        disabled={Boolean(busy)}
        onQuery={setQuery}
        onSearch={applySearch}
        onRefresh={refreshAfterAction}
        pagination={pagination}
      />
      {error && !refreshError && !busy && (
        <div role="alert">
          回收站读取失败{" "}
          <button className="text-button" onClick={refreshAfterAction}>
            重试
          </button>
        </div>
      )}
      {!data && !error ? (
        <PageLoadingState title="Listing 回收站" label="正在读取回收站…" />
      ) : data ? (
        <>
          <div className="recycle-table-wrap">
            <table className="recycle-table">
              <thead>
                <tr>
                  <th>Listing / 店铺</th>
                  <th>所属任务</th>
                  <th>移除人</th>
                  <th>移除时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <b>{item.scope.listing || "--"}</b>
                      <small>{item.scope.store || "--"}</small>
                    </td>
                    <td>
                      <button
                        className="text-button"
                        onClick={() =>
                          navigateHash("analysis-tasks", { task_id: item.task_id })
                        }
                      >
                        {item.task_title}
                      </button>
                    </td>
                    <td>{item.removed_by}</td>
                    <td>{formatTime(item.deleted_at)}</td>
                    <td>
                      <TaskRecycleRowActions
                        item={item}
                        disabled={Boolean(busy)}
                        onRestore={() => act(item, "restore")}
                        onPurge={() => setPurging(item)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data.items.length && (
              <p className="listing-table-empty">
                <span>{search ? "没有匹配的移除记录" : "回收站为空"}</span>
                {search && (
                  <button
                    className="text-button"
                    disabled={Boolean(busy)}
                    onClick={() => applySearch("")}
                  >
                    清除搜索，查看全部
                  </button>
                )}
              </p>
            )}
          </div>
          <fieldset
            className="recycle-pagination recycle-pager"
            disabled={pagination.disabled}
            role="group"
            aria-label="回收站底部分页"
          >
            <Pagination {...pagination} showTotal={false} />
          </fieldset>
        </>
      ) : null}
      {purging && (
        <TaskRecyclePurgeDialog
          item={purging}
          busy={Boolean(busy)}
          onClose={() => setPurging(null)}
          onConfirm={() => act(purging, "purge")}
        />
      )}
    </div>
  );
}
