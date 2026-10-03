import { ArrowLeft, Plus, Pulse } from "@phosphor-icons/react";
import { EmptyState, PageHeading, PageLoadingState } from "../../components/SharedUi";
import { TaskDetail } from "./TaskDetail";
import { TaskRegistry } from "./TaskRegistry";
import { useTaskMonitorState } from "./useTaskMonitorState";
import { taskLifecycleActions } from "./taskLifecycleActions";
import { taskExecutionActions } from "./taskExecutionActions";
import { errorMessage } from "./taskMonitorRequests";

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
  } = state;
  return (
    <div className="standard-page task-page task-runtime-workspace">
      <div hidden={showTaskDetail}>
        <PageHeading
          title="分析任务"
          action={
            <button className="primary-button" onClick={() => onNavigate("new")}>
              <Plus size={18} />
              新建任务
            </button>
          }
        />
        <TaskRegistry
          tasks={tasks}
          selectedId={selectedId}
          viewState={listState}
          onViewStateChange={updateListState}
          loading={loading}
          error={listError}
          hasData={taskData !== undefined}
          onReload={loadTasks}
          onCreate={() => onNavigate("new")}
          onOpen={openTask}
          onCreateSimilar={(/** @type {AnalysisTask} */ task) =>
            onNavigate("new", { kind: "task-template", id: task.id })
          }
          onArchive={archiveTasks}
        />
      </div>
      {showTaskDetail && (
        <section className="task-detail-panel">
          <button className="task-back-button" onClick={returnToList}>
            <ArrowLeft size={17} /> 全部任务
          </button>
          {!visibleSelected && !detailError && (
            <PageLoadingState label="正在读取任务…" />
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
                    loadSelected().catch((error) =>
                      setDetailError(errorMessage(error)),
                    );
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
              ) =>
                onNavigate("classification-results", {
                  kind: "classification-result",
                  id: segment.result_version_id,
                  taskId: selected.id,
                  segmentId: segment.id || segment.segment_key,
                  listing: segment.scope?.listing,
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
