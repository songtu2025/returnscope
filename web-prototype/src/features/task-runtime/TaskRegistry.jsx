import { Archive, ArrowCounterClockwise } from "@phosphor-icons/react";
import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import {
  canArchiveTask,
  matchesQuery,
  sortTasks,
  taskFilterGroup,
  taskSummary,
} from "./taskRegistryPolicy";
import { TaskRegistryFilters } from "./TaskRegistryFilters";
import { TaskRegistryRow } from "./TaskRegistryRow";
import { TaskRegistryStates } from "./TaskRegistryStates";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/**
 * @typedef {Object} TaskRegistryProps
 * @property {AnalysisTask[]} tasks
 * @property {string | null} selectedId
 * @property {{filter: string, query: string, owner: string, sort: string, attentionOnly: boolean}} viewState
 * @property {(changes: Partial<TaskRegistryProps["viewState"]>) => void} onViewStateChange
 * @property {boolean} loading
 * @property {string} error
 * @property {boolean} hasData
 * @property {() => void | Promise<unknown>} onReload
 * @property {() => void} onCreate
 * @property {(task: AnalysisTask) => void} onOpen
 * @property {(taskIds: string[], archived: boolean) => Promise<boolean>} onArchive
 * @property {(task: AnalysisTask) => void} onCreateSimilar
 */
/** @param {TaskRegistryProps} props */
export function TaskRegistry({
  tasks,
  selectedId,
  viewState,
  onViewStateChange,
  loading,
  error,
  hasData,
  onReload,
  onCreate,
  onOpen,
  onArchive,
  onCreateSimilar,
}) {
  const { filter, query, owner, sort, attentionOnly } = viewState;
  const deferredQuery = useDeferredValue(query.trim().toLocaleLowerCase());
  const [selectedIds, setSelectedIds] = useState(
    () => new Set(/** @type {string[]} */ ([])),
  );
  const [saving, setSaving] = useState(false);
  const selectAllRef = useRef(/** @type {HTMLInputElement | null} */ (null));
  const searchInputRef = useRef(/** @type {HTMLInputElement | null} */ (null));

  const owners = useMemo(
    () =>
      [...new Set(tasks.map((task) => task.owner_name).filter(Boolean))].sort((a, b) =>
        a.localeCompare(b, "zh-CN"),
      ),
    [tasks],
  );
  const counts = useMemo(
    () =>
      tasks.reduce(
        (current, task) => {
          current[taskFilterGroup(task)] += 1;
          if (!task.archived_at) current.all += 1;
          return current;
        },
        /** @type {Record<string, number>} */ ({
          all: 0,
          active: 0,
          finished: 0,
          archived: 0,
        }),
      ),
    [tasks],
  );
  const visibleTasks = useMemo(() => {
    const values = tasks.filter(
      (task) =>
        (filter === "all" ? !task.archived_at : taskFilterGroup(task) === filter) &&
        (!attentionOnly || taskSummary(task).needsAttention) &&
        (owner === "all" || task.owner_name === owner) &&
        matchesQuery(task, deferredQuery),
    );
    return sortTasks(values, sort);
  }, [attentionOnly, deferredQuery, filter, owner, sort, tasks]);
  const selectableTasks = useMemo(
    () => visibleTasks.filter(canArchiveTask),
    [visibleTasks],
  );
  const selectedVisibleIds = selectableTasks
    .filter((task) => selectedIds.has(task.id))
    .map((task) => task.id);
  const allSelected =
    selectableTasks.length > 0 && selectedVisibleIds.length === selectableTasks.length;

  useEffect(() => {
    setSelectedIds(new Set());
  }, [filter]);

  useEffect(() => {
    const availableIds = new Set(tasks.map((task) => task.id));
    setSelectedIds((current) => {
      const next = new Set([...current].filter((id) => availableIds.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [tasks]);

  useEffect(() => {
    if (!selectAllRef.current) return;
    selectAllRef.current.indeterminate = selectedVisibleIds.length > 0 && !allSelected;
  }, [allSelected, selectedVisibleIds.length]);

  /** @param {string} taskId */
  const toggleTask = (taskId) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });
  };

  const toggleAll = () => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allSelected) selectableTasks.forEach((task) => next.delete(task.id));
      else selectableTasks.forEach((task) => next.add(task.id));
      return next;
    });
  };

  /** @param {string[]} taskIds @param {boolean} archived */
  const applyArchive = async (taskIds, archived) => {
    setSaving(true);
    try {
      const saved = await onArchive(taskIds, archived);
      if (saved) setSelectedIds(new Set());
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="task-list-panel task-registry" aria-label="任务列表">
      <TaskRegistryFilters
        viewState={viewState}
        onViewStateChange={onViewStateChange}
        owners={owners}
        counts={counts}
        searchInputRef={searchInputRef}
      />

      <TaskRegistryStates
        loading={loading}
        error={error}
        hasData={hasData}
        tasks={tasks}
        visibleCount={visibleTasks.length}
        deferredQuery={deferredQuery}
        owner={owner}
        filter={filter}
        onReload={onReload}
        onCreate={onCreate}
      />
      {!loading && (!error || hasData) && visibleTasks.length > 0 && (
        <div className="task-registry-table" role="table" aria-label="任务管理表">
          <div className="task-registry-head" role="row">
            <span role="columnheader">
              <input
                ref={selectAllRef}
                type="checkbox"
                checked={allSelected}
                disabled={selectableTasks.length === 0}
                onChange={toggleAll}
                aria-label="选择当前列表中的可管理任务"
              />
            </span>
            <span role="columnheader">任务</span>
            <span role="columnheader">执行状态</span>
            <span role="columnheader">进度</span>
            <span role="columnheader">结果与待办</span>
            <span role="columnheader">最近更新</span>
            <span role="columnheader">操作</span>
          </div>
          {visibleTasks.map((task) => (
            <TaskRegistryRow
              key={task.id}
              task={task}
              active={selectedId === task.id}
              selected={selectedIds.has(task.id)}
              selectable={canArchiveTask(task)}
              saving={saving}
              onToggle={() => toggleTask(task.id)}
              onOpen={() => onOpen(task)}
              onCreateSimilar={() => onCreateSimilar(task)}
              onArchive={() => applyArchive([task.id], !task.archived_at)}
            />
          ))}
        </div>
      )}

      {selectedVisibleIds.length > 0 && (
        <div className="task-registry-batch" role="region" aria-label="批量任务操作">
          <b>已选择 {selectedVisibleIds.length} 个任务</b>
          <div>
            <button
              className="secondary-button"
              disabled={saving}
              onClick={() => applyArchive(selectedVisibleIds, filter !== "archived")}
            >
              {filter === "archived" ? (
                <ArrowCounterClockwise size={17} />
              ) : (
                <Archive size={17} />
              )}
              {filter === "archived" ? "恢复" : "归档"}
            </button>
            <button
              className="secondary-button"
              disabled={saving}
              onClick={() => setSelectedIds(new Set())}
            >
              取消选择
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
