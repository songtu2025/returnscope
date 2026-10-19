import { ArrowLeft, Plus, Pulse } from "@phosphor-icons/react";
import { EmptyState, PageHeading, PageLoadingState } from "../../components/SharedUi";
import { navigateHash } from "../../app/hashRouter";
import { TaskDetail } from "./TaskDetail";
import { TaskRegistry } from "./TaskRegistry";
import { useTaskMonitorState } from "./useTaskMonitorState";
import { taskLifecycleActions } from "./taskLifecycleActions";
import { taskExecutionActions } from "./taskExecutionActions";
import { useListReturnPosition } from "../../hooks/useListReturnPosition";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment */

/** @param {import("./taskMonitorContracts").TaskMonitorProps} props */
export function TaskMonitor(props) {
  const state = useTaskMonitorState(props);
  const { notify, onNavigate, onTaskFocus, focusSegmentId = null } = props;
  const {
    listState,
    selectedId,
    selected,
    events,
    actionError,
    openTask,
    detailError,
    taskData,
    tasks,
    listError,
    listRefreshError,
    refreshingList,
    loading,
    loadTasks,
    loadSelected,
    showTaskDetail,
    visibleSelected,
    returnToList,
    archiveTasks,
    setActionError,
    setDetailError,
    updateListState,
    onTaskRenamed,
  } = state;
  const { containerRef, titleRef, remember } = useListReturnPosition({
    identity: JSON.stringify(listState),
    active: !showTaskDetail && !props.focusId,
    ready: !loading && (taskData !== undefined || Boolean(listError)),
    snapshotRef: props.returnPosition,
  });
  return (
    <div className="standard-page task-page task-runtime-workspace">
      <div hidden={showTaskDetail} ref={containerRef}>
        <PageHeading
          title="分析任务"
          titleRef={titleRef}
          action={
            <div className="recycle-actions">
              <button
                className="secondary-button"
                onClick={() => navigateHash("analysis-tasks", { view: "recycle" })}
              >
                回收站
              </button>
              <button className="primary-button" onClick={() => onNavigate("new")}>
                <Plus size={18} />
                新建任务
              </button>
            </div>
          }
        />
        <TaskRegistry
          tasks={tasks}
          selectedId={selectedId}
          viewState={listState}
          onViewStateChange={updateListState}
          loading={loading && !showTaskDetail}
          error={listError}
          hasData={taskData !== undefined}
          onReload={loadTasks}
          onCreate={() => onNavigate("new")}
          onOpen={(task) => {
            remember(task.id);
            openTask(task);
          }}
          onTaskRenamed={onTaskRenamed}
          onCreateSimilar={(/** @type {AnalysisTask} */ task) =>
            onNavigate("new", { kind: "task-template", id: task.id })
          }
          onArchive={archiveTasks}
        />
      </div>
      {showTaskDetail && (
        <section className="task-detail-panel">
          <button
            className="task-back-button page-loading-navigation"
            onClick={
              props.onReturnRecycle ||
              props.onReturnResultPool ||
              props.onReturnProducts ||
              returnToList
            }
          >
            <ArrowLeft size={17} />{" "}
            {props.onReturnRecycle
              ? "返回 Listing 回收站"
              : props.onReturnResultPool
                ? "返回分类结果池"
                : props.onReturnProducts
                  ? "返回产品信息"
                  : listState.ownerId === undefined
                    ? "全部任务"
                    : "返回我的任务"}
          </button>
          {listRefreshError && (
            <div className="task-action-error" role="alert">
              <span>操作结果已保留，任务列表刷新失败 · {listRefreshError}</span>
              <button
                className="secondary-button"
                disabled={refreshingList}
                onClick={() => loadTasks(true)}
              >
                {refreshingList ? "刷新中…" : "刷新任务列表"}
              </button>
            </div>
          )}
          {!visibleSelected && !detailError && (
            <PageLoadingState title="分析任务" label="正在读取任务…" />
          )}
          {visibleSelected && detailError && (
            <div className="task-action-error" role="alert">
              <span>任务更新失败，当前显示上一次数据 · {detailError}</span>
              <button
                className="secondary-button"
                onClick={() => loadSelected().catch(() => {})}
              >
                重新加载
              </button>
            </div>
          )}
          {!visibleSelected && detailError && (
            <EmptyState
              icon={Pulse}
              title="任务读取失败"
              description={detailError}
              action={
                <button
                  className="secondary-button"
                  onClick={() => {
                    setDetailError("");
                    loadSelected().catch(() => {});
                  }}
                >
                  重新加载
                </button>
              }
            />
          )}
          {selected && selected.id === selectedId && (
            <TaskDetail
              key={selected.id}
              task={selected}
              listingReturnState={props.listingReturnState}
              onTaskRenamed={onTaskRenamed}
              {...taskLifecycleActions({
                ...state,
                notify,
                onNavigate,
                onTaskFocus,
                selected,
              })}
              {...taskExecutionActions({
                ...state,
                notify,
                onNavigate,
                onTaskFocus,
                selected,
              })}
              onArchive={() => archiveTasks([selected.id], !selected.archived_at)}
              focusSegmentId={focusSegmentId}
              events={events}
              onViewClassification={(
                /** @type {TaskSegment & {result_version_id: string}} */ segment,
                /** @type {string | undefined} */ qualityStatus,
                /** @type {string | undefined} */ systemRerunRequired,
              ) =>
                onNavigate("classification-results", {
                  kind: "classification-result",
                  id: segment.result_version_id,
                  taskId: selected.id,
                  ...(props.taskReturn ? { taskReturn: props.taskReturn } : {}),
                  segmentId: segment.id || segment.segment_key,
                  listing: segment.scope?.listing,
                  recordQualityStatus: qualityStatus,
                  systemRerunRequired,
                })
              }
              actionError={actionError}
              onClearActionError={() => setActionError("")}
            />
          )}
        </section>
      )}
    </div>
  );
}
