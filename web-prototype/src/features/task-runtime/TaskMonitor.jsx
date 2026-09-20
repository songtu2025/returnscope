import { useCallback, useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { ArrowLeft, Plus, Pulse } from "@phosphor-icons/react";
import { api } from "../../api";
import { EmptyState, InlineLoading, PageHeading } from "../../components/SharedUi";
import { serverStateKeys } from "../../shared/serverState";
import { TaskDetail } from "./TaskDetail";
import { TaskRegistry } from "./TaskRegistry";

/**
 * @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment
 * @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask
 * @typedef {import("./taskRuntimeContracts").TaskPayload} TaskPayload
 * @typedef {import("./taskRuntimeContracts").TaskEvent} TaskEvent
 * @typedef {import("./taskRuntimeContracts").SegmentAction} SegmentAction
 *
 * @typedef {Object} TaskMonitorProps
 * @property {(message: string, type?: "success" | "error") => void} notify
 * @property {import("../../app/navigation").Navigate} onNavigate
 * @property {() => void | Promise<unknown>} onChanged
 * @property {string | null} [focusId]
 * @property {string | null} [focusSegmentId]
 * @property {TaskListState} [listState]
 * @property {(changes: Partial<TaskListState>) => void} [onListStateChange]
 * @property {(taskId: string | null) => void} [onTaskFocus]
 */

/** @typedef {{filter: string, query: string, owner: string, sort: string, attentionOnly: boolean}} TaskListState */

/**
 * 当前组件使用的任务 API 响应契约。静态类型集中在消费边界，不改变请求行为。
 * @type {{
 *   tasks: (filters?: Record<string, string | number | boolean | null | undefined>, options?: RequestInit) => Promise<AnalysisTask[]>,
 *   task: (id: string, options?: RequestInit) => Promise<AnalysisTask>,
 *   archiveTasks: (taskIds: string[], archived: boolean) => Promise<unknown>,
 *   eventUrl: (taskId: string, after?: number) => string,
 *   renameTask: (id: string, payload: TaskPayload) => Promise<AnalysisTask>,
 *   cancelTask: (id: string, payload: TaskPayload) => Promise<unknown>,
 *   pauseTask: (id: string, payload: TaskPayload) => Promise<AnalysisTask>,
 *   resumeTask: (id: string, payload: TaskPayload) => Promise<AnalysisTask>,
 *   retryTask: (id: string) => Promise<AnalysisTask>,
 *   retryTaskSegment: (id: string, segmentKey: string, payload: TaskPayload) => Promise<AnalysisTask>,
 *   retrySegmentResultPublish: (id: string, segmentId: string, payload: TaskPayload) => Promise<AnalysisTask>,
 *   controlTaskSegment: (id: string, segmentKey: string, action: SegmentAction, payload: TaskPayload) => Promise<AnalysisTask>,
 *   setTaskParallelism: (id: string, payload: TaskPayload) => Promise<AnalysisTask>,
 *   reorderTaskSegments: (id: string, payload: TaskPayload) => Promise<AnalysisTask>,
 *   preflightTaskReplan: (id: string, payload: TaskPayload) => Promise<import("../task-planning/taskPlanContracts").TaskExecutionPlan>,
 *   replanTask: (id: string, payload: TaskPayload) => Promise<AnalysisTask>
 * }}
 */
const taskMonitorApi = api;
const ACTIVE_LIST_REFRESH_MS = 10000;
const IDLE_LIST_REFRESH_MS = 60000;
const DEFAULT_LIST_STATE = {
  filter: "all",
  query: "",
  owner: "all",
  sort: "updated_desc",
  attentionOnly: false,
};
const EMPTY_TASKS = /** @type {AnalysisTask[]} */ ([]);

/** @param {unknown} error */
function errorMessage(error) {
  return error instanceof Error ? error.message : "请求失败";
}

/** @param {unknown} error */
function errorStatus(error) {
  return typeof error === "object" && error !== null && "status" in error
    ? error.status
    : undefined;
}

/** @param {TaskMonitorProps} props */
export function TaskMonitor({
  notify,
  onNavigate,
  onChanged,
  focusId,
  focusSegmentId = null,
  listState: controlledListState,
  onListStateChange,
  onTaskFocus,
}) {
  const [localListState, setLocalListState] = useState(DEFAULT_LIST_STATE);
  const listState = controlledListState ?? localListState;
  const [selectedId, setSelectedId] = useState(/** @type {string | null} */ (null));
  const [selected, setSelected] = useState(/** @type {AnalysisTask | null} */ (null));
  const [events, setEvents] = useState(/** @type {TaskEvent[]} */ ([]));
  const [eventStreamVersion, setEventStreamVersion] = useState(0);
  const [actionError, setActionError] = useState("");
  const selectedRequestGeneration = useRef(0);
  const previousFocusId = useRef(/** @type {string | null | undefined} */ (focusId));
  const listScroll = useRef(0);
  const notifiedListError = useRef("");
  const [detailError, setDetailError] = useState("");

  const {
    data: taskData,
    error: taskListError,
    isLoading,
    mutate: refreshTasks,
  } = useSWR(serverStateKeys.taskList, () =>
    taskMonitorApi.tasks({ include_archived: true }),
  );
  const tasks = /** @type {AnalysisTask[]} */ (taskData ?? EMPTY_TASKS);
  const listError = taskListError ? errorMessage(taskListError) : "";
  const loading = isLoading && taskData === undefined;

  useEffect(() => {
    if (!taskListError) {
      notifiedListError.current = "";
      return;
    }
    if (taskData !== undefined) return;
    const message = errorMessage(taskListError);
    if (notifiedListError.current === message) return;
    notifiedListError.current = message;
    notify(message, "error");
  }, [notify, taskData, taskListError]);

  /** @param {Partial<TaskListState>} changes */
  const updateListState = (changes) => {
    if (onListStateChange) {
      onListStateChange(changes);
      return;
    }
    setLocalListState((current) => ({ ...current, ...changes }));
  };

  const loadTasks = useCallback(
    /** @param {boolean} [silent] */
    async (silent = false) => {
      try {
        await refreshTasks();
      } catch (error) {
        if (!silent) notify(errorMessage(error), "error");
      }
    },
    [notify, refreshTasks],
  );

  const loadSelected = useCallback(
    /** @param {RequestInit} [options] */
    async (options = {}) => {
      if (!selectedId) return null;
      const generation = ++selectedRequestGeneration.current;
      const value = await taskMonitorApi.task(selectedId, options);
      if (selectedRequestGeneration.current === generation) setSelected(value);
      return value;
    },
    [selectedId],
  );

  useEffect(() => {
    const previous = previousFocusId.current;
    previousFocusId.current = focusId;
    if (focusId) {
      setSelectedId(focusId);
      return;
    }
    if (previous) {
      setSelectedId(null);
    }
  }, [focusId]);
  useEffect(() => {
    const controller = new AbortController();
    setSelected(null);
    setDetailError("");
    setActionError("");
    if (!selectedId) {
      selectedRequestGeneration.current += 1;
      setSelected(null);
      return () => controller.abort();
    }
    loadSelected({ signal: controller.signal }).catch((error) => {
      if (
        (!(error instanceof Error) || error.name !== "AbortError") &&
        !controller.signal.aborted
      )
        setDetailError(errorMessage(error));
    });
    return () => {
      controller.abort();
      selectedRequestGeneration.current += 1;
    };
  }, [loadSelected, notify, selectedId]);
  useEffect(() => {
    if (!selectedId) return undefined;
    setEvents([]);
    /** @type {number | null} */
    let refreshTimer = null;
    /** @type {TaskEvent[]} */
    let pendingEvents = [];
    const source = new EventSource(taskMonitorApi.eventUrl(selectedId), {
      withCredentials: true,
    });
    source.addEventListener("task", (event) => {
      const value = /** @type {TaskEvent} */ (JSON.parse(event.data));
      pendingEvents.push(value);
      if (refreshTimer !== null) return;
      refreshTimer = window.setTimeout(() => {
        refreshTimer = null;
        const nextEvents = pendingEvents;
        pendingEvents = [];
        setEvents((current) => [...current, ...nextEvents]);
        Promise.all([loadSelected(), loadTasks(true), onChanged()]).catch((error) =>
          notify(errorMessage(error), "error"),
        );
      }, 500);
    });
    source.addEventListener("close", () => source.close());
    return () => {
      source.close();
      if (refreshTimer !== null) window.clearTimeout(refreshTimer);
    };
  }, [selectedId, eventStreamVersion, loadSelected, loadTasks, notify, onChanged]);

  useEffect(() => {
    if (selectedId) return undefined;
    const hasActiveTasks = tasks.some((task) =>
      ["queued", "running"].includes(task.status),
    );
    const timer = window.setInterval(
      () => {
        if (!document.hidden) loadTasks(true);
      },
      hasActiveTasks ? ACTIVE_LIST_REFRESH_MS : IDLE_LIST_REFRESH_MS,
    );
    const frame = window.requestAnimationFrame(() =>
      window.scrollTo(0, listScroll.current),
    );
    return () => {
      window.clearInterval(timer);
      window.cancelAnimationFrame(frame);
    };
  }, [selectedId, loadTasks, tasks]);

  useEffect(() => {
    if (selectedId) return undefined;
    const refreshWhenVisible = () => {
      if (!document.hidden) loadTasks(true);
    };
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => document.removeEventListener("visibilitychange", refreshWhenVisible);
  }, [selectedId, loadTasks]);

  const showTaskDetail = Boolean(selectedId);
  const returnToList = () => {
    setSelectedId(null);
    if (onTaskFocus) onTaskFocus(null);
    else onNavigate("analysis-tasks");
  };

  /** @param {string[]} taskIds @param {boolean} archived */
  const archiveTasks = async (taskIds, archived) => {
    try {
      await taskMonitorApi.archiveTasks(taskIds, archived);
      await loadTasks();
      if (selectedId && taskIds.includes(selectedId)) await loadSelected();
      notify(archived ? "任务已归档" : "任务已恢复");
      return true;
    } catch (error) {
      notify(errorMessage(error), "error");
      return false;
    }
  };

  return (
    <div className="standard-page task-page task-runtime-workspace">
      <div hidden={showTaskDetail}>
        <PageHeading
          title="分析任务"
          description="查看分析进展，处理问题，使用已有结果。"
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
          onOpen={(/** @type {AnalysisTask} */ task) => {
            listScroll.current = window.scrollY;
            window.scrollTo(0, 0);
            setSelectedId(task.id);
            if (onTaskFocus) onTaskFocus(task.id);
            else onNavigate("analysis-tasks", { kind: "task", id: task.id });
          }}
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
          {!selected && !detailError && <InlineLoading label="正在读取任务…" />}
          {!selected && detailError && (
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
          {selected && (
            <TaskDetail
              key={selected.id}
              task={selected}
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
              onRename={async (/** @type {TaskPayload} */ payload) => {
                try {
                  const updated = await taskMonitorApi.renameTask(selected.id, payload);
                  setSelected(updated);
                  await loadTasks();
                  setEventStreamVersion((current) => current + 1);
                  notify("任务名称已修改并记录操作人");
                  return true;
                } catch (error) {
                  if (errorStatus(error) === 409) await loadSelected();
                  notify(errorMessage(error), "error");
                  return false;
                }
              }}
              onCancel={async (/** @type {TaskPayload} */ payload) => {
                try {
                  await taskMonitorApi.cancelTask(selected.id, payload);
                  notify("取消请求已提交");
                  await loadTasks();
                  await loadSelected();
                  return true;
                } catch (error) {
                  if (errorStatus(error) === 409) await loadSelected();
                  notify(errorMessage(error), "error");
                  return false;
                }
              }}
              onPause={async () => {
                try {
                  const updated = await taskMonitorApi.pauseTask(selected.id, {
                    expected_revision: selected.revision,
                  });
                  setSelected(updated);
                  await loadTasks();
                  notify("未完成 Listing 正在安全暂停");
                  return true;
                } catch (error) {
                  if (errorStatus(error) === 409) await loadSelected();
                  notify(errorMessage(error), "error");
                  return false;
                }
              }}
              onResume={async (/** @type {TaskPayload} */ payload) => {
                try {
                  const updated = await taskMonitorApi.resumeTask(selected.id, payload);
                  setSelected(updated);
                  setActionError("");
                  await loadTasks();
                  updateListState({ filter: "active" });
                  notify(
                    selected.status === "cancelled"
                      ? "未完成 Listing 已重新排队"
                      : "未完成 Listing 已继续排队",
                  );
                  return true;
                } catch (error) {
                  if (errorStatus(error) === 409) {
                    setActionError("任务版本已变化，请查看刷新后的状态再操作。");
                    await loadSelected();
                  }
                  notify(errorMessage(error), "error");
                  return false;
                }
              }}
              onRetry={async () => {
                try {
                  const retried = await taskMonitorApi.retryTask(selected.id);
                  await loadTasks();
                  setSelectedId(retried.id);
                  if (onTaskFocus) onTaskFocus(retried.id);
                  else onNavigate("analysis-tasks", { kind: "task", id: retried.id });
                  notify(
                    selected.status === "completed"
                      ? "已按原快照创建再次运行任务"
                      : "重试任务已进入队列",
                  );
                } catch (error) {
                  notify(errorMessage(error), "error");
                }
              }}
              onRetrySegment={async (
                /** @type {string} */ segmentKey,
                /** @type {TaskPayload} */ payload,
              ) => {
                try {
                  const updated = await taskMonitorApi.retryTaskSegment(
                    selected.id,
                    segmentKey,
                    payload,
                  );
                  setSelected(updated);
                  setActionError("");
                  await loadTasks();
                  notify("任务片段已重新排队");
                  return true;
                } catch (error) {
                  if (errorStatus(error) === 409) {
                    setActionError("任务版本已变化，请查看刷新后的片段状态再操作。");
                    await loadSelected();
                  } else {
                    setActionError(errorMessage(error));
                  }
                  notify(errorMessage(error), "error");
                  return false;
                }
              }}
              onRetryResultPublish={async (/** @type {string} */ segmentId) => {
                try {
                  const updated = await taskMonitorApi.retrySegmentResultPublish(
                    selected.id,
                    segmentId,
                    {
                      expected_revision: selected.revision,
                      reason: "重新发布分类结果",
                    },
                  );
                  setSelected(updated);
                  setActionError("");
                  await loadTasks();
                  notify("分类结果正在重新生成");
                  return true;
                } catch (error) {
                  if (errorStatus(error) === 409) await loadSelected();
                  notify(errorMessage(error), "error");
                  return false;
                }
              }}
              onSegmentAction={async (
                /** @type {string} */ segmentKey,
                /** @type {SegmentAction} */ action,
                /** @type {string} */ note = "",
              ) => {
                try {
                  const updated = await taskMonitorApi.controlTaskSegment(
                    selected.id,
                    segmentKey,
                    action,
                    {
                      expected_revision: selected.revision,
                      note,
                    },
                  );
                  setSelected(updated);
                  setActionError("");
                  await loadTasks();
                  notify(
                    {
                      pause: "Listing 暂停请求已提交",
                      resume: "Listing 已重新进入等待队列",
                      cancel: "Listing 取消请求已提交",
                    }[action],
                  );
                  return true;
                } catch (error) {
                  if (errorStatus(error) === 409) await loadSelected();
                  notify(errorMessage(error), "error");
                  return false;
                }
              }}
              onParallelism={async (/** @type {number} */ maxParallelSegments) => {
                try {
                  const updated = await taskMonitorApi.setTaskParallelism(selected.id, {
                    expected_revision: selected.revision,
                    max_parallel_segments: maxParallelSegments,
                  });
                  setSelected(updated);
                  setActionError("");
                  notify(`Listing 并行数已调整为 ${maxParallelSegments}`);
                  return true;
                } catch (error) {
                  if (errorStatus(error) === 409) await loadSelected();
                  notify(errorMessage(error), "error");
                  return false;
                }
              }}
              onReorderSegments={async (/** @type {string[]} */ segmentKeys) => {
                try {
                  const updated = await taskMonitorApi.reorderTaskSegments(
                    selected.id,
                    {
                      expected_revision: selected.revision,
                      segment_keys: segmentKeys,
                    },
                  );
                  setSelected(updated);
                  setActionError("");
                  notify("执行顺序已更新，将在当前片段完成后生效");
                  return true;
                } catch (error) {
                  if (errorStatus(error) === 409) {
                    setActionError("等待片段已经变化，请刷新后重新排序。");
                    await loadSelected();
                  }
                  notify(errorMessage(error), "error");
                  return false;
                }
              }}
              onPreflightReplan={(/** @type {TaskPayload} */ payload) =>
                taskMonitorApi.preflightTaskReplan(selected.id, payload)
              }
              onReplan={async (/** @type {TaskPayload} */ payload) => {
                try {
                  const updated = await taskMonitorApi.replanTask(selected.id, payload);
                  setSelected(updated);
                  setActionError("");
                  await loadTasks();
                  notify("任务执行计划已更新");
                  return true;
                } catch (error) {
                  if (errorStatus(error) === 409) {
                    setActionError("执行计划或任务版本已变化，请重新预检后再提交。");
                    await loadSelected();
                  }
                  notify(errorMessage(error), "error");
                  return false;
                }
              }}
            />
          )}
        </section>
      )}
    </div>
  );
}
