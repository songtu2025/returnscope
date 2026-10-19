import "./taskRecycle.css";
import { useEffect, useState } from "react";
import { useDataRefresh } from "../../hooks/useDataRefresh";
import { ArrowLeft } from "@phosphor-icons/react";
import { PageHeading, PageLoadingState } from "../../components/SharedUi";
import { TaskRecycleTable } from "./TaskRecycleTable";
import { TaskRecycleSelection, TaskRecycleBatchResult } from "./TaskRecycleBatch";
import { useTaskRecycleData } from "./useTaskRecycleData";
import { useTaskRecycleActions } from "./useTaskRecycleActions";
import { TaskRecycleActionDialog } from "./TaskRecycleDialogs";
import { TaskRecycleToolbar } from "./TaskRecycleToolbar";
import { Pagination } from "../../components/Pagination";
import { navigateHash } from "../../app/hashRouter";
import { useUnsavedNavigation } from "../../hooks/useUnsavedNavigation";
import { useListReturnPosition } from "../../hooks/useListReturnPosition";
import { useTaskRecycleView } from "./useTaskRecycleView";

/** @param {{notify: (message: string, type?: "success" | "error") => void, routeQuery?: Record<string, string | undefined>, returnPosition?: import("react").MutableRefObject<import("../../hooks/useListReturnPosition").ListReturnPosition | null>}} props */
export function TaskRecyclePage({ notify, routeQuery, returnPosition }) {
  const { query, setQuery, search, page, pageSize, update, returnHash } =
    useTaskRecycleView(routeQuery);
  const setPage = (/** @type {number} */ value) => update({ page: value });
  const [selected, setSelected] = useState(/** @type {string[]} */ ([]));
  useEffect(() => {
    setSelected([]);
  }, [returnHash]);
  const dataState = useTaskRecycleData({ search, page, pageSize, setPage });
  const {
    data,
    error,
    totalData,
    totalError,
    refreshError,
    refresh,
    refreshAfterAction,
  } = dataState;
  const { containerRef, titleRef, remember } = useListReturnPosition({
    identity: returnHash,
    ready: Boolean(data || error),
    snapshotRef: returnPosition,
  });
  const openTask = (
    /** @type {import("./taskRecycleContracts").RecycledListing} */ item,
    segment = false,
  ) => {
    remember(item.id);
    navigateHash("analysis-tasks", {
      task_id: item.task_id,
      segment_id: segment ? item.id : "",
      recycle_return: returnHash,
    });
  };
  const actions = useTaskRecycleActions({
    notify,
    ...dataState,
    clearSelection: () => setSelected([]),
  });
  const {
    busy,
    blocked,
    restored,
    confirmation,
    setConfirmation,
    result,
    execute,
    verifyResult,
  } = actions;
  const visibleSelection = selected.filter((id) =>
    data?.items.some((item) => item.id === id),
  );
  const selectedItems =
    data?.items.filter((item) => visibleSelection.includes(item.id)) ?? [];
  useUnsavedNavigation({
    dirty: false,
    busy,
    canSave: false,
    save: async () => false,
    onRequest: () => notify("操作处理中，完成后再离开"),
  });
  const changePage = (/** @type {number} */ value) => {
    setSelected([]);
    setPage(value);
  };
  useDataRefresh(refresh, {
    domains: ["task-recycle"],
    loading: blocked,
    identity: `${search}:${page}:${pageSize}`,
  });
  const applySearch = (/** @type {string} */ value) => {
    setSelected([]);
    setQuery(value);
    update({ search: value, page: 1 });
  };
  const pagination = {
    page,
    pageSize,
    total: data?.total ?? 0,
    totalPages: Math.max(1, Math.ceil((data?.total ?? 0) / pageSize)),
    disabled: blocked || !data,
    onPage: changePage,
    onPageSize: (/** @type {number} */ size) => {
      setSelected([]);
      update({ pageSize: size, page: 1 });
    },
    showQuickJumper: true,
  };
  return (
    <div className="standard-page task-page task-runtime-workspace" ref={containerRef}>
      <button
        className="task-back-button"
        disabled={busy}
        onClick={() => navigateHash("analysis-tasks")}
      >
        <ArrowLeft size={17} />
        全部任务
      </button>
      <PageHeading title="Listing 回收站" titleRef={titleRef} />
      {restored && (
        <div className="recycle-restore-result" role="status" aria-label="恢复结果">
          <span>{restored.scope.listing || "Listing"} 已恢复，不会自动执行</span>
          <button
            className="text-button"
            disabled={busy}
            onClick={() => openTask(restored, true)}
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
            disabled={blocked}
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
        disabled={blocked}
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
          <TaskRecycleSelection
            count={visibleSelection.length}
            disabled={blocked}
            onClear={() => setSelected([])}
            onRestore={() =>
              setConfirmation({ items: selectedItems, action: "restore" })
            }
            onPurge={() => setConfirmation({ items: selectedItems, action: "purge" })}
          />
          <TaskRecycleTable
            items={data.items}
            selected={visibleSelection}
            disabled={blocked}
            onSelect={setSelected}
            onTask={openTask}
            onRestore={(item) => execute([item], "restore")}
            onPurge={(item) => setConfirmation({ items: [item], action: "purge" })}
          />
          <div>
            {!data.items.length && (
              <p className="listing-table-empty">
                <span>{search ? "没有匹配的移除记录" : "回收站为空"}</span>
                {search && (
                  <button
                    className="text-button"
                    disabled={blocked}
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
      {result && (
        <TaskRecycleBatchResult result={result} busy={busy} onVerify={verifyResult} />
      )}
      {confirmation && (
        <TaskRecycleActionDialog
          {...confirmation}
          busy={Boolean(busy)}
          onClose={() => setConfirmation(null)}
          onConfirm={() => execute(confirmation.items, confirmation.action)}
        />
      )}
    </div>
  );
}
