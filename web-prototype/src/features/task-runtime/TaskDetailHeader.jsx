import { useDismissibleDetails } from "../../hooks/useDismissibleDetails";
import {
  Archive,
  ArrowClockwise,
  ChartBar,
  DotsThreeVertical,
  DownloadSimple,
  GearSix,
  Pause,
  PlayCircle,
  X,
} from "@phosphor-icons/react";
import Button from "antd/es/button";
import { api } from "../../api";
import { classNames, formatTime } from "../../lib/presentation";
import { FINAL_TASK_STATUSES } from "./taskRegistryPolicy";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {ReturnType<typeof import("./taskRegistryPolicy").taskSummary>} TaskSummary */
/**
 * @typedef {Object} TaskDetailHeaderProps
 * @property {AnalysisTask} task
 * @property {TaskSummary} summary
 * @property {boolean | undefined} hasUnfinishedSegments
 * @property {() => void} onOpenReplan
 * @property {() => void} onOpenResume
 * @property {() => void} onOpenRename
 * @property {() => void} onOpenCancel
 * @property {() => void | Promise<unknown>} onPause
 * @property {() => void | Promise<unknown>} onRetry
 * @property {() => void | Promise<unknown>} onArchive
 * @property {(filter: string) => void} showListings
 */

/** @param {Pick<TaskDetailHeaderProps, "task" | "summary" | "hasUnfinishedSegments" | "onOpenReplan" | "onOpenResume">} props */
function TaskRecoveryActions({
  task,
  summary,
  hasUnfinishedSegments,
  onOpenReplan,
  onOpenResume,
}) {
  return (
    <>
      {(task.status === "blocked" ||
        (task.status === "partial" && summary.remaining > 0)) && (
        <Button type="primary" className="primary-button" onClick={onOpenReplan}>
          <ArrowClockwise size={17} />
          重新预检 / 规划
        </Button>
      )}
      {["paused", "cancelled"].includes(task.status) && hasUnfinishedSegments && (
        <Button type="primary" className="primary-button" onClick={onOpenResume}>
          <PlayCircle size={17} />
          {task.status === "cancelled" ? "重新排队未完成" : "继续未完成"}
        </Button>
      )}
    </>
  );
}

/** @param {Pick<TaskDetailHeaderProps, "task" | "summary" | "onPause" | "onRetry" | "showListings">} props */
function TaskExecutionActions({ task, summary, onPause, onRetry, showListings }) {
  return (
    <>
      {["queued", "running"].includes(task.status) && (
        <Button type="primary" className="primary-button" onClick={onPause}>
          <Pause size={17} /> 暂停未完成
        </Button>
      )}
      {task.status === "failed" && (
        <Button type="primary" className="primary-button" onClick={onRetry}>
          <ArrowClockwise size={17} /> 重新运行
        </Button>
      )}
      {summary.generated > 0 && (
        <Button
          type={task.status === "completed" ? "primary" : "default"}
          className={
            task.status === "completed" ? "primary-button" : "secondary-button"
          }
          onClick={() => showListings("delivered")}
        >
          <ChartBar size={17} /> 查看已有结果
        </Button>
      )}
    </>
  );
}

/** @param {Pick<TaskDetailHeaderProps, "task" | "onRetry" | "onArchive" | "onOpenRename" | "onOpenCancel">} props */
function TaskMoreActions({ task, onRetry, onArchive, onOpenRename, onOpenCancel }) {
  const { detailsProps, summaryProps } = useDismissibleDetails({ menu: true });
  return (
    <details {...detailsProps} className="task-more-actions">
      <summary {...summaryProps} aria-label="更多任务操作" title="更多任务操作">
        <DotsThreeVertical size={19} />
      </summary>
      <div>
        {task.result_file_path && (
          <a href={api.downloadUrl(task.id)}>
            <DownloadSimple size={16} />
            {task.status === "cancelled" ? "下载部分结果" : "下载结果"}
          </a>
        )}
        <button onClick={onOpenRename}>
          <GearSix size={16} /> 修改名称
        </button>
        {task.status === "completed" && (
          <button onClick={onRetry}>
            <ArrowClockwise size={16} /> 再次运行
          </button>
        )}
        {(task.archived_at || FINAL_TASK_STATUSES.includes(task.status)) && (
          <button onClick={onArchive}>
            <Archive size={16} />
            {task.archived_at ? "恢复任务" : "归档任务"}
          </button>
        )}
        {["queued", "running", "paused"].includes(task.status) && (
          <button className="danger" onClick={onOpenCancel}>
            <X size={16} />
            取消未完成
          </button>
        )}
      </div>
    </details>
  );
}

/** @param {TaskDetailHeaderProps} props */
export function TaskDetailHeader({
  task,
  summary,
  hasUnfinishedSegments,
  onOpenReplan,
  onOpenResume,
  onOpenRename,
  onOpenCancel,
  onPause,
  onRetry,
  onArchive,
  showListings,
}) {
  return (
    <header className="task-command-header">
      <div className="task-detail-summary">
        <div className="task-title-row">
          <h2>{task.title}</h2>
          <span className={classNames("task-status-badge", task.status)}>
            {summary.statusLabel}
          </span>
        </div>
        <p>
          {task.store || task.dataset_name} · {task.owner_name} ·{" "}
          {formatTime(task.created_at)}
        </p>
      </div>
      <div className="detail-actions">
        <TaskRecoveryActions
          task={task}
          summary={summary}
          hasUnfinishedSegments={hasUnfinishedSegments}
          onOpenReplan={onOpenReplan}
          onOpenResume={onOpenResume}
        />
        <TaskExecutionActions
          task={task}
          summary={summary}
          onPause={onPause}
          onRetry={onRetry}
          showListings={showListings}
        />
        <TaskMoreActions
          task={task}
          onRetry={onRetry}
          onArchive={onArchive}
          onOpenRename={onOpenRename}
          onOpenCancel={onOpenCancel}
        />
      </div>
    </header>
  );
}
