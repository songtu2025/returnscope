import {
  Archive,
  ArrowCounterClockwise,
  CopySimple,
  DotsThreeVertical,
  MagnifyingGlass,
  PlayCircle,
  SlidersHorizontal,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";

import { EmptyState, InlineLoading, StatusPill } from "../../components/SharedUi";
import { classNames, formatTime } from "../../lib/presentation";
import {
  FINAL_TASK_STATUSES,
  taskFilterGroup,
  taskSummary,
} from "./taskRegistryPolicy";

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
/**
 * @typedef {Object} TaskRegistryRowProps
 * @property {AnalysisTask} task
 * @property {boolean} active
 * @property {boolean} selected
 * @property {boolean} selectable
 * @property {boolean} saving
 * @property {() => void} onToggle
 * @property {() => void} onOpen
 * @property {() => void} onCreateSimilar
 * @property {() => void} onArchive
 */

const FILTERS = [
  ["all", "全部"],
  ["active", "未结束"],
  ["finished", "已结束"],
  ["archived", "已归档"],
];

/** @param {AnalysisTask} task */
function canArchiveTask(task) {
  return Boolean(task.archived_at) || FINAL_TASK_STATUSES.includes(task.status);
}

/** @param {AnalysisTask} task @param {string} query */
function matchesQuery(task, query) {
  if (!query) return true;
  const source = [
    task.title,
    task.store,
    task.listing,
    task.listing_search_text,
    task.dataset_name,
    task.owner_name,
  ]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase();
  return source.includes(query);
}

/** @param {AnalysisTask[]} tasks @param {string} sort */
function sortTasks(tasks, sort) {
  return [...tasks].sort((left, right) => {
    if (sort === "created_desc") {
      return String(right.created_at).localeCompare(String(left.created_at));
    }
    if (sort === "progress_desc") {
      return Number(right.progress_percent || 0) - Number(left.progress_percent || 0);
    }
    return String(right.updated_at || right.created_at).localeCompare(
      String(left.updated_at || left.created_at),
    );
  });
}

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
      <div className="task-registry-toolbar">
        <label className="task-registry-search">
          <MagnifyingGlass size={18} />
          <input
            ref={searchInputRef}
            value={query}
            onChange={(event) => onViewStateChange({ query: event.target.value })}
            placeholder="搜索任务、店铺或 Listing"
            aria-label="搜索任务、店铺或 Listing"
          />
          {query && (
            <button
              type="button"
              onClick={() => {
                onViewStateChange({ query: "" });
                searchInputRef.current?.focus();
              }}
              aria-label="清空搜索"
            >
              <X size={15} />
            </button>
          )}
        </label>
        <details className="task-registry-filter-menu">
          <summary>
            <SlidersHorizontal size={17} /> 筛选与排序{owner !== "all" ? " · 1" : ""}
          </summary>
          <div className="task-registry-controls">
            <select
              value={owner}
              onChange={(event) => onViewStateChange({ owner: event.target.value })}
              aria-label="按负责人筛选"
            >
              <option value="all">全部负责人</option>
              {owners.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            <select
              value={sort}
              onChange={(event) => onViewStateChange({ sort: event.target.value })}
              aria-label="任务排序"
            >
              <option value="updated_desc">最近更新</option>
              <option value="created_desc">最近创建</option>
              <option value="progress_desc">进度从高到低</option>
            </select>
          </div>
        </details>
      </div>

      <div className="task-registry-tabs" aria-label="任务筛选">
        {FILTERS.map(([value, label]) => (
          <button
            key={value}
            className={filter === value ? "active" : ""}
            onClick={() => onViewStateChange({ filter: value })}
            aria-pressed={filter === value}
            aria-label={label}
          >
            {label}
            <span>{counts[value]}</span>
          </button>
        ))}
        <label className="task-attention-filter">
          <input
            type="checkbox"
            checked={attentionOnly}
            onChange={(event) =>
              onViewStateChange({ attentionOnly: event.target.checked })
            }
          />
          只看需处理
        </label>
      </div>

      {loading && <InlineLoading label="读取任务…" />}
      {!loading && error && (
        <div className="task-list-error" role="alert">
          <EmptyState
            icon={WarningCircle}
            title={
              hasData ? "任务列表更新失败，当前显示上一次数据" : "任务列表读取失败"
            }
            description={error}
            action={
              <button className="secondary-button" onClick={onReload}>
                重新加载
              </button>
            }
          />
        </div>
      )}
      {!loading && (!error || hasData) && visibleTasks.length === 0 && (
        <EmptyState
          icon={PlayCircle}
          title={deferredQuery || owner !== "all" ? "没有匹配任务" : "暂无任务"}
          description={
            deferredQuery || owner !== "all"
              ? "请调整搜索词或筛选条件。"
              : filter === "active"
                ? "新任务开始后，会在这里展示实时进度。"
                : "当前分组中没有任务记录。"
          }
          action={
            tasks.length === 0 ? (
              <button className="primary-button" onClick={onCreate}>
                创建分析任务
              </button>
            ) : null
          }
        />
      )}
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

/** @param {TaskRegistryRowProps} props */
function TaskRegistryRow({
  task,
  active,
  selected,
  selectable,
  saving,
  onToggle,
  onOpen,
  onCreateSimilar,
  onArchive,
}) {
  const summary = taskSummary(task);
  return (
    <div
      className={classNames(
        "task-registry-row",
        active && "active",
        selected && "selected",
      )}
      role="row"
      aria-current={active ? "true" : undefined}
    >
      <span role="cell" className="task-registry-check">
        <input
          type="checkbox"
          checked={selected}
          disabled={!selectable || saving}
          onChange={onToggle}
          aria-label={`选择任务：${task.title}`}
        />
      </span>
      <span role="cell" className="task-registry-identity">
        <button type="button" onClick={onOpen}>
          <b>{task.title}</b>
          <small>
            {[task.store, task.owner_name].filter(Boolean).join(" · ") || "分析任务"}
          </small>
        </button>
      </span>
      <span role="cell" className="task-registry-status">
        <StatusPill status={task.status} label={summary.statusLabel} />
      </span>
      <span role="cell" className="task-registry-progress">
        <b>{Math.round(task.progress_percent || 0)}%</b>
        <span aria-label={`任务进度 ${Math.round(task.progress_percent || 0)}%`}>
          <i style={{ width: `${task.progress_percent || 0}%` }} />
        </span>
        <small>
          {(task.progress_current || 0).toLocaleString()} /{" "}
          {(task.progress_total || 0).toLocaleString()}
        </small>
      </span>
      <span role="cell" className="task-registry-results">
        <b>
          {summary.generated} / {summary.total} 个 Listing 已生成结果
        </b>
        {summary.resultDescription && <small>{summary.resultDescription}</small>}
        {summary.issueDescription && (
          <small className="task-issue-text">{summary.issueDescription}</small>
        )}
      </span>
      <time role="cell" dateTime={task.updated_at || task.created_at}>
        {formatTime(task.updated_at || task.created_at)}
      </time>
      <span role="cell" className="task-registry-actions">
        <button type="button" className="task-open-action" onClick={onOpen}>
          查看
        </button>
        <details>
          <summary aria-label={`更多任务操作：${task.title}`}>
            <DotsThreeVertical size={18} />
          </summary>
          <div className="task-registry-menu">
            <button type="button" onClick={onCreateSimilar}>
              <CopySimple size={16} />
              创建类似任务
            </button>
            {selectable && (
              <button type="button" onClick={onArchive} disabled={saving}>
                {task.archived_at ? (
                  <ArrowCounterClockwise size={16} />
                ) : (
                  <Archive size={16} />
                )}
                {task.archived_at ? "恢复任务" : "归档任务"}
              </button>
            )}
          </div>
        </details>
      </span>
    </div>
  );
}
