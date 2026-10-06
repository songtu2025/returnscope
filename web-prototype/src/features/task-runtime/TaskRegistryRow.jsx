import {
  Archive,
  ArrowCounterClockwise,
  CopySimple,
  DotsThreeVertical,
} from "@phosphor-icons/react";
import { StatusPill } from "../../components/SharedUi";
import { classNames, formatTime } from "../../lib/presentation";
import { taskSummary } from "./taskRegistryPolicy";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
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

/** @param {TaskRegistryRowProps} props */
export function TaskRegistryRow({
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
      <RegistryIdentity task={task} onOpen={onOpen} />
      <span role="cell" className="task-registry-status">
        <StatusPill status={task.status} label={summary.statusLabel} />
      </span>
      <RegistryProgress task={task} />
      <RegistryResults summary={summary} />
      <time role="cell" dateTime={task.updated_at || task.created_at}>
        {formatTime(task.updated_at || task.created_at)}
      </time>
      <RegistryActions
        task={task}
        selectable={selectable}
        saving={saving}
        onOpen={onOpen}
        onCreateSimilar={onCreateSimilar}
        onArchive={onArchive}
      />
    </div>
  );
}

/** @param {Pick<TaskRegistryRowProps, "task" | "onOpen">} props */
function RegistryIdentity({ task, onOpen }) {
  return (
    <span role="cell" className="task-registry-identity">
      <button type="button" onClick={onOpen}>
        <b>{task.title}</b>
        <small>
          {[task.store, task.owner_name].filter(Boolean).join(" · ") || "分析任务"}
        </small>
      </button>
    </span>
  );
}

/** @param {Pick<TaskRegistryRowProps, "task">} props */
function RegistryProgress({ task }) {
  return (
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
  );
}

/** @param {{summary: ReturnType<typeof taskSummary>}} props */
function RegistryResults({ summary }) {
  return (
    <span role="cell" className="task-registry-results">
      <b>
        {summary.generated} / {summary.total} 个 Listing 已生成结果
      </b>
      {summary.resultDescription && <small>{summary.resultDescription}</small>}
      {summary.issueDescription && (
        <small className="task-issue-text">{summary.issueDescription}</small>
      )}
    </span>
  );
}

/** @param {Pick<TaskRegistryRowProps, "task" | "selectable" | "saving" | "onOpen" | "onCreateSimilar" | "onArchive">} props */
function RegistryActions({
  task,
  selectable,
  saving,
  onOpen,
  onCreateSimilar,
  onArchive,
}) {
  return (
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
  );
}
