import { useDataRefresh } from "../../hooks/useDataRefresh";
import {
  MANAGED_REFRESH_OPTIONS,
  REFRESH_INTERVALS,
  notifyDataChanged,
} from "../../shared/refreshPolicy";
import { useCallback, useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import {
  refreshServerState,
  refreshTaskNameState,
  serverStateKeys,
} from "../../shared/serverState";
import { taskMonitorApi, errorMessage } from "./taskMonitorRequests";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskEvent} TaskEvent */
/** @typedef {import("./taskMonitorContracts").TaskListState} TaskListState */

const DEFAULT_LIST_STATE = {
  filter: "all",
  query: "",
  owner: "all",
  sort: "updated_desc",
  attentionOnly: false,
};
const EMPTY_TASKS = /** @type {AnalysisTask[]} */ ([]);
const fetchTaskList = () => taskMonitorApi.tasks({ include_archived: true });

/** @param {import("./taskMonitorContracts").TaskMonitorProps} props */
export function useTaskMonitorState({
  notify,
  onNavigate,
  onChanged,
  focusId,
  listState: controlledListState,
  onListStateChange,
  onTaskFocus,
}) {
  const { mutate: mutateCache } = useSWRConfig();
  const [localListState, setLocalListState] = useState(DEFAULT_LIST_STATE);
  const listState = controlledListState ?? localListState;
  const [selectedId, setSelectedId] = useState(/** @type {string | null} */ (null));
  const [selected, setSelected] = useState(/** @type {AnalysisTask | null} */ (null));
  const [events, setEvents] = useState(/** @type {TaskEvent[]} */ ([]));
  const [eventStreamVersion, setEventStreamVersion] = useState(0);
  const [actionError, setActionError] = useState("");
  const selectedRequestGeneration = useRef(0);
  const selectedControllerRef = useRef(/** @type {AbortController | null} */ (null));
  const previousFocusId = useRef(/** @type {string | null | undefined} */ (focusId));
  const notifiedListError = useRef("");
  const [detailError, setDetailError] = useState("");
  const [listRefreshError, setListRefreshError] = useState("");
  const [refreshingList, setRefreshingList] = useState(false);

  const {
    data: taskData,
    error: taskListError,
    isValidating,
    mutate: refreshTasks,
  } = useSWR(serverStateKeys.taskList, fetchTaskList, MANAGED_REFRESH_OPTIONS);
  const tasks = /** @type {AnalysisTask[]} */ (taskData ?? EMPTY_TASKS);
  const listError =
    listRefreshError || (taskListError ? errorMessage(taskListError) : "");
  const loading = isValidating;

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
      setRefreshingList(true);
      try {
        await refreshTasks(fetchTaskList, { revalidate: false });
        setListRefreshError("");
        return true;
      } catch (error) {
        setListRefreshError(errorMessage(error));
        if (!silent) notify(errorMessage(error), "error");
        return false;
      } finally {
        setRefreshingList(false);
      }
    },
    [notify, refreshTasks],
  );

  const loadSelected = useCallback(
    /** @param {RequestInit} [options] */
    async (options = {}) => {
      if (!selectedId) return null;
      const generation = ++selectedRequestGeneration.current;
      selectedControllerRef.current?.abort();
      const controller = new AbortController();
      selectedControllerRef.current = controller;
      const signal = options.signal ?? controller.signal;
      try {
        const value = await taskMonitorApi.task(selectedId, { ...options, signal });
        if (selectedRequestGeneration.current === generation && !signal.aborted) {
          setSelected(value);
          setDetailError("");
        }
        return value;
      } catch (error) {
        if (selectedRequestGeneration.current === generation && !signal.aborted)
          setDetailError(errorMessage(error));
        throw error;
      }
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
    // 请求错误由 loadSelected 写入详情状态。
    loadSelected({ signal: controller.signal }).catch(() => {});
    return () => {
      controller.abort();
      selectedControllerRef.current?.abort();
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
        notifyDataChanged(["analysis-tasks"]);
        void refreshServerState(mutateCache, [
          "classification-results",
          "analysis-dashboards",
          "workbench",
        ]).catch(() => notify("关联数据更新失败，可重试", "error"));
      }, 500);
    });
    source.addEventListener("close", () => source.close());
    return () => {
      source.close();
      if (refreshTimer !== null) window.clearTimeout(refreshTimer);
    };
  }, [
    selectedId,
    eventStreamVersion,
    loadSelected,
    loadTasks,
    notify,
    onChanged,
    mutateCache,
  ]);

  const hasActiveTasks = tasks.some((task) =>
    ["queued", "running"].includes(task.status),
  );
  const activeSelection = selectedId
    ? ["queued", "running"].includes(selected?.status ?? "")
    : hasActiveTasks;
  useDataRefresh(
    async () => {
      if (!selectedId) return loadTasks(true);
      await Promise.all([loadSelected(), loadTasks(true), onChanged()]);
    },
    {
      interval: activeSelection
        ? REFRESH_INTERVALS.activeTask
        : REFRESH_INTERVALS.ordinary,
      domains: ["analysis-tasks"],
      identity: selectedId || "list",
      loading: loading && !taskData,
    },
  );

  const showTaskDetail = Boolean(selectedId);
  const visibleSelected = selected?.id === selectedId ? selected : null;
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

  /** @param {AnalysisTask} updated */
  const onTaskRenamed = async (updated) => {
    const previousTitle =
      tasks.find((task) => task.id === updated.id)?.title ?? selected?.title ?? "";
    setSelected(updated);
    await Promise.all([
      loadTasks(),
      refreshTaskNameState(mutateCache, updated, previousTitle),
    ]);
    setEventStreamVersion((current) => current + 1);
    notify("任务名称已修改");
  };

  /** @param {AnalysisTask} task */
  const openTask = (task) => {
    window.scrollTo(0, 0);
    setSelectedId(task.id);
    if (onTaskFocus) onTaskFocus(task.id);
    else onNavigate("analysis-tasks", { kind: "task", id: task.id });
  };

  return {
    mutateCache,
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
    updateListState,
    loadTasks,
    loadSelected,
    showTaskDetail,
    visibleSelected,
    returnToList,
    archiveTasks,
    onTaskRenamed,
    setSelectedId,
    setSelected,
    setActionError,
    setDetailError,
    setEventStreamVersion,
  };
}
