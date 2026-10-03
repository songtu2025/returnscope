import { useCallback, useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { serverStateKeys } from "../../shared/serverState";
import { taskMonitorApi, errorMessage } from "./taskMonitorRequests";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskEvent} TaskEvent */
/** @typedef {import("./taskMonitorContracts").TaskListState} TaskListState */

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

  /** @param {AnalysisTask} task */
  const openTask = (task) => {
    listScroll.current = window.scrollY;
    window.scrollTo(0, 0);
    setSelectedId(task.id);
    if (onTaskFocus) onTaskFocus(task.id);
    else onNavigate("analysis-tasks", { kind: "task", id: task.id });
  };

  return {
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
    updateListState,
    loadTasks,
    loadSelected,
    showTaskDetail,
    visibleSelected,
    returnToList,
    archiveTasks,
    setSelectedId,
    setSelected,
    setActionError,
    setDetailError,
    setEventStreamVersion,
  };
}
