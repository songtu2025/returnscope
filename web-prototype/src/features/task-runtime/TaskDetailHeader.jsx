import { ResultDownloadButton } from "../classification-results/ResultDownloadButton";
import { TaskNameEditor } from "./TaskNameEditor";
import { useDismissibleDetails } from "../../hooks/useDismissibleDetails";
import {
  Archive,
  ArrowClockwise,
  ChartBar,
  CopySimple,
  DotsThreeVertical,
  DownloadSimple,
  Pause,
  PlayCircle,
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
 * @property {(disabled: boolean) => import("react").ReactNode} [headerAction]
 * @property {string} [taskAction]
 * @property {TaskSummary} summary
 * @property {boolean | undefined} hasUnfinishedSegments
 * @property {() => void} onOpenReplan
 * @property {() => void} onOpenResume
 * @property {(task: AnalysisTask) => Promise<unknown>} onTaskRenamed
 * @property {() => void} [onCreateSimilar]
 * @property {() => void | Promise<unknown>} onPause
 * @property {() => void | Promise<unknown>} onRetry
 * @property {() => void | Promise<unknown>} onArchive
 * @property {() => void} onViewResults
 */

/** @param {Pick<TaskDetailHeaderProps, "task" | "taskAction" | "summary" | "hasUnfinishedSegments" | "onOpenReplan" | "onOpenResume">} props */
function TaskRecoveryActions({
  task,
  taskAction,
  summary,
  hasUnfinishedSegments,
  onOpenReplan,
  onOpenResume,
}) {
  return (
    <>
      {(task.status === "blocked" ||
        (task.status === "partial" && summary.remaining > 0)) && (
        <Button
          type="primary"
          className="primary-button"
          disabled={Boolean(taskAction)}
          onClick={onOpenReplan}
        >
          <ArrowClockwise size={17} />
          重新预检 / 规划
        </Button>
      )}
      {["paused", "cancelled"].includes(task.status) && hasUnfinishedSegments && (
        <Button
          type="primary"
          className="primary-button"
          disabled={Boolean(taskAction)}
          onClick={onOpenResume}
        >
          <PlayCircle size={17} />
          {task.status === "cancelled" ? "重新排队未完成" : "继续未完成"}
        </Button>
      )}
    </>
  );
}

/** @param {Pick<TaskDetailHeaderProps, "task" | "taskAction" | "summary" | "onPause" | "onRetry" | "onViewResults">} props */
function TaskExecutionActions({
  task,
  taskAction,
  summary,
  onPause,
  onRetry,
  onViewResults,
}) {
  return (
    <>
      {["queued", "running"].includes(task.status) && (
        <Button
          type="primary"
          className="primary-button"
          disabled={Boolean(taskAction)}
          onClick={onPause}
        >
          <Pause size={17} /> {taskAction === "pause" ? "正在暂停…" : "暂停未完成"}
        </Button>
      )}
      {task.status === "failed" && (
        <Button
          type="primary"
          className="primary-button"
          disabled={Boolean(taskAction)}
          onClick={onRetry}
        >
          <ArrowClockwise size={17} />{" "}
          {taskAction === "retry" ? "正在创建任务…" : "重新运行"}
        </Button>
      )}
      {summary.generated > 0 && (
        <Button
          type={task.status === "completed" ? "primary" : "default"}
          className={
            task.status === "completed" ? "primary-button" : "secondary-button"
          }
          onClick={onViewResults}
        >
          <ChartBar size={17} /> 查看已有结果
        </Button>
      )}
    </>
  );
}

/** @param {Pick<TaskDetailHeaderProps, "task" | "taskAction" | "onRetry" | "onArchive" | "onCreateSimilar">} props */
function TaskMoreActions({ task, taskAction, onRetry, onArchive, onCreateSimilar }) {
  const { detailsProps, summaryProps } = useDismissibleDetails({ menu: true });
  const versionIds = (task.segments ?? [])
    .filter((item) => !item.deleted_at && item.result_version_id)
    .map((item) => String(item.result_version_id));
  return (
    <details {...detailsProps} className="task-more-actions">
      <summary {...summaryProps} aria-label="更多任务操作" title="更多任务操作">
        <DotsThreeVertical size={19} />
      </summary>
      <div>
        {onCreateSimilar && (
          <button disabled={Boolean(taskAction)} onClick={onCreateSimilar}>
            <CopySimple size={16} /> 创建类似任务
          </button>
        )}
        {versionIds.length > 0 && (
          <ResultDownloadButton
            key={versionIds.join(":")}
            versionIds={versionIds}
            label={task.status === "cancelled" ? "下载部分结果" : "下载结果"}
          />
        )}
        {task.result_file_path && versionIds.length === 0 && (
          <a href={api.downloadUrl(task.id)}>
            <DownloadSimple size={16} />
            {task.status === "cancelled" ? "下载部分结果" : "下载结果"}
          </a>
        )}
        {task.status === "completed" && (
          <button disabled={Boolean(taskAction)} onClick={onRetry}>
            <ArrowClockwise size={16} /> 再次运行
          </button>
        )}
        {(task.archived_at || FINAL_TASK_STATUSES.includes(task.status)) && (
          <button disabled={Boolean(taskAction)} onClick={onArchive}>
            <Archive size={16} />
            {task.archived_at ? "恢复任务" : "归档任务"}
          </button>
        )}
      </div>
    </details>
  );
}

/** @param {TaskDetailHeaderProps} props */
export function TaskDetailHeader({
  task,
  headerAction,
  taskAction = "",
  summary,
  hasUnfinishedSegments,
  onOpenReplan,
  onOpenResume,
  onTaskRenamed,
  onCreateSimilar,
  onPause,
  onRetry,
  onArchive,
  onViewResults,
}) {
  return (
    <header className="task-command-header">
      <div className="task-detail-summary">
        <div className="task-title-row">
          <TaskNameEditor
            task={task}
            onSaved={onTaskRenamed}
            heading
            disabled={Boolean(taskAction)}
          />
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
        {headerAction?.(Boolean(taskAction))}
        <TaskRecoveryActions
          task={task}
          taskAction={taskAction}
          summary={summary}
          hasUnfinishedSegments={hasUnfinishedSegments}
          onOpenReplan={onOpenReplan}
          onOpenResume={onOpenResume}
        />
        <TaskExecutionActions
          task={task}
          taskAction={taskAction}
          summary={summary}
          onPause={onPause}
          onRetry={onRetry}
          onViewResults={onViewResults}
        />
        <TaskMoreActions
          task={task}
          taskAction={taskAction}
          onRetry={onRetry}
          onArchive={onArchive}
          onCreateSimilar={onCreateSimilar}
        />
        {taskAction && (
          <span role="status">
            {
              {
                pause: "正在暂停…",
                retry: "正在创建任务…",
                resume: "正在提交继续执行…",
                archive: task.archived_at ? "正在恢复任务…" : "正在归档任务…",
                segment: "正在更新 Listing…",
                publish: "正在生成分类结果…",
                parallelism: "正在调整并行数…",
                order: "正在调整执行顺序…",
                "retry-segment": "正在提交 Listing 重试…",
                replan: "正在更新执行计划…",
              }[taskAction]
            }
          </span>
        )}
      </div>
    </header>
  );
}
