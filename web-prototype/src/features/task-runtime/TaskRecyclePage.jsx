import "./taskRecycle.css";
import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { useDataRefresh } from "../../hooks/useDataRefresh";
import { refreshServerState } from "../../shared/serverState";
import { ArrowLeft } from "@phosphor-icons/react";
import { taskApi } from "../../shared/api/taskApi";
import { request } from "../../shared/api/request";
import { errorMessage } from "../../shared/api/requestErrors";
import { Modal, PageHeading, PageLoadingState } from "../../components/SharedUi";
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
  const [busy, setBusy] = useState("");
  const [restored, setRestored] = useState(
    /** @type {RecycledListing | null} */ (null),
  );
  const [refreshError, setRefreshError] = useState(false);
  const [purging, setPurging] = useState(/** @type {RecycledListing | null} */ (null));
  const readRecycle = async () =>
    /** @type {{items: RecycledListing[], total: number}} */ (
      await request(`/api/tasks/recycle?q=${encodeURIComponent(search)}&page=${page}`)
    );
  const { data, error, mutate } = useSWR(
    ["task-recycle", search, page],
    readRecycle,
    MANAGED_REFRESH_OPTIONS,
  );
  const refresh = async () => {
    const next = await mutate(readRecycle, { revalidate: false });
    if (next && page > Math.max(1, Math.ceil(next.total / 20)))
      setPage(Math.max(1, Math.ceil(next.total / 20)));
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
    identity: `${search}:${page}`,
  });
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
        <div className="recycle-restore-result" role="status">
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
      <form
        className="listing-queue-toolbar recycle-search-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (busy) return;
          setSearch(query.trim());
          setPage(1);
        }}
      >
        <label className="listing-queue-search">
          <input
            aria-label="搜索回收站"
            placeholder="搜索 Listing、店铺或所属任务"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <button className="secondary-button" disabled={Boolean(busy)}>
          搜索
        </button>
      </form>
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
                      <div className="recycle-actions">
                        <button
                          className="secondary-button compact-button"
                          disabled={Boolean(busy)}
                          onClick={() => act(item, "restore")}
                        >
                          恢复
                        </button>
                        <button
                          className="text-button danger"
                          disabled={Boolean(busy)}
                          onClick={() => setPurging(item)}
                        >
                          永久删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data.items.length && (
              <p className="listing-table-empty">
                {search ? "没有匹配的移除记录" : "回收站为空"}
              </p>
            )}
          </div>
          <div className="recycle-pagination">
            <span>
              共 {data.total} 条 · 第 {page} 页
            </span>
            <button
              className="secondary-button compact-button"
              disabled={Boolean(busy) || page <= 1}
              onClick={() => setPage(page - 1)}
            >
              上一页
            </button>
            <button
              className="secondary-button compact-button"
              disabled={Boolean(busy) || page * 20 >= data.total}
              onClick={() => setPage(page + 1)}
            >
              下一页
            </button>
          </div>
        </>
      ) : null}
      {purging && (
        <Modal
          title={`永久删除 ${purging.scope.listing || "Listing"}`}
          onClose={() => !busy && setPurging(null)}
        >
          <p>
            执行项及其独占检查点、旧导出文件将永久清理，无法恢复。已有分类结果、看板和必要来源信息保留。
          </p>
          <div className="modal-actions">
            <button
              className="secondary-button"
              disabled={Boolean(busy)}
              onClick={() => setPurging(null)}
            >
              返回
            </button>
            <button
              className="danger-button"
              disabled={Boolean(busy)}
              onClick={() => act(purging, "purge")}
            >
              {busy ? "正在删除…" : "确认永久删除"}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
