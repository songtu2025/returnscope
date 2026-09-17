import { useEffect, useState } from "react";
import {
  Archive,
  ArrowClockwise,
  ChartBar,
  DotsThreeVertical,
  DownloadSimple,
  GearSix,
  Pause,
  PlayCircle,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import Button from "antd/es/button";
import { api } from "../../api";
import { AntdProvider } from "../../components/AntdProvider";
import { InfoRow } from "../../components/SharedUi";
import { EFFORT_LABELS } from "../../constants";
import { classNames, formatTime } from "../../lib/presentation";
import {
  SegmentCancelDialog,
  SegmentRetryDialog,
  TaskCancelDialog,
  TaskRenameDialog,
  TaskResumeDialog,
} from "./TaskActionDialogs";
import { SegmentBoard } from "./SegmentBoard";
import { TaskEventList } from "./TaskEventList";
import { TaskReplanDialog } from "./TaskReplanDialog";

import { FINAL_TASK_STATUSES, taskSummary } from "./taskRegistryPolicy";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskEvent} TaskEvent */
/** @typedef {import("./taskRuntimeContracts").TaskPayload} TaskPayload */
/** @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment */
/** @typedef {import("./taskRuntimeContracts").SegmentAction} SegmentAction */
/** @typedef {import("../task-planning/taskPlanContracts").TaskExecutionPlan} TaskExecutionPlan */
/**
 * @typedef {Object} TaskDetailProps
 * @property {AnalysisTask} task
 * @property {string | null} [focusSegmentId]
 * @property {TaskEvent[]} events
 * @property {(segment: TaskSegment & {result_version_id: string}) => void} onViewClassification
 * @property {string} actionError
 * @property {() => void} onClearActionError
 * @property {(payload: TaskPayload) => Promise<boolean>} onRename
 * @property {() => void | Promise<unknown>} onArchive
 * @property {(payload: TaskPayload) => Promise<boolean>} onCancel
 * @property {() => void | Promise<unknown>} onPause
 * @property {(payload: TaskPayload) => Promise<boolean>} onResume
 * @property {() => void | Promise<unknown>} onRetry
 * @property {(segmentKey: string, payload: TaskPayload) => Promise<boolean>} onRetrySegment
 * @property {(segmentId: string) => Promise<boolean>} onRetryResultPublish
 * @property {(segmentKey: string, action: SegmentAction, note?: string) => Promise<boolean>} onSegmentAction
 * @property {(maxParallelSegments: number) => Promise<boolean>} onParallelism
 * @property {(segmentKeys: string[]) => Promise<boolean>} onReorderSegments
 * @property {(payload: TaskPayload) => Promise<TaskExecutionPlan>} onPreflightReplan
 * @property {(payload: TaskPayload) => Promise<boolean>} onReplan
 */

const DETAIL_TABS = [
  ["execution", "Listing"],
  ["events", "运行日志"],
  ["config", "任务配置"],
];
/** @param {TaskDetailProps} props */
export function TaskDetail({
  task,
  focusSegmentId,
  events,
  onViewClassification,
  actionError,
  onClearActionError,
  onRename,
  onArchive,
  onCancel,
  onPause,
  onResume,
  onRetry,
  onRetrySegment,
  onRetryResultPublish,
  onSegmentAction,
  onParallelism,
  onReorderSegments,
  onPreflightReplan,
  onReplan,
}) {
  const [renameOpen, setRenameOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [resumeOpen, setResumeOpen] = useState(false);
  const [retrySegment, setRetrySegment] = useState(
    /** @type {TaskSegment | null} */ (null),
  );
  const [cancelSegment, setCancelSegment] = useState(
    /** @type {TaskSegment | null} */ (null),
  );
  const [replanOpen, setReplanOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("execution");
  const [listingFilter, setListingFilter] = useState("all");
  const summary = taskSummary(task);
  const isActive = ["queued", "running", "paused"].includes(task.status);
  useEffect(() => {
    if (focusSegmentId) {
      setActiveTab("execution");
      setListingFilter("all");
    }
  }, [focusSegmentId]);
  /** @param {string} filter */
  const showListings = (filter) => {
    setListingFilter(filter);
    setActiveTab("execution");
  };
  const hasUnfinishedSegments = task.segments?.some((segment) =>
    [
      "cancelled",
      "not_started",
      "running",
      "queued",
      "retry_pending",
      "paused",
    ].includes(segment.status),
  );
  const executableSegments =
    task.segments?.filter((segment) => segment.agent_key !== "unknown") ?? [];
  const modelServiceIssue = executableSegments.find(
    (segment) =>
      ["paused", "failed", "running"].includes(segment.status) &&
      Number(segment.model_failures || 0) >= 3 &&
      segment.error,
  );
  const remainingSegments = summary.remaining;
  const firstStandard = executableSegments.find((segment) => segment.standard_name);

  return (
    <AntdProvider>
      <>
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
            {(task.status === "blocked" ||
              (task.status === "partial" && remainingSegments > 0)) && (
              <Button
                type="primary"
                className="primary-button"
                onClick={() => setReplanOpen(true)}
              >
                <ArrowClockwise size={17} />
                重新预检 / 规划
              </Button>
            )}
            {["paused", "cancelled"].includes(task.status) && hasUnfinishedSegments && (
              <Button
                type="primary"
                className="primary-button"
                onClick={() => setResumeOpen(true)}
              >
                <PlayCircle size={17} />
                {task.status === "cancelled" ? "重新排队未完成" : "继续未完成"}
              </Button>
            )}
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
            <details className="task-more-actions">
              <summary aria-label="更多任务操作" title="更多任务操作">
                <DotsThreeVertical size={19} />
              </summary>
              <div>
                {task.result_file_path && (
                  <a href={api.downloadUrl(task.id)}>
                    <DownloadSimple size={16} />
                    {task.status === "cancelled" ? "下载部分结果" : "下载结果"}
                  </a>
                )}
                <button onClick={() => setRenameOpen(true)}>
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
                  <button className="danger" onClick={() => setCancelOpen(true)}>
                    <X size={16} />
                    取消未完成
                  </button>
                )}
              </div>
            </details>
          </div>
        </header>

        {actionError && !retrySegment && (
          <div className="task-action-error" role="alert">
            <WarningCircle size={18} />
            <span>{actionError}</span>
            <Button type="text" onClick={onClearActionError}>
              关闭
            </Button>
          </div>
        )}

        {["failed", "blocked", "partial"].includes(task.status) && task.message && (
          <section className="task-action-banner" role="status">
            <WarningCircle size={19} />
            <div>
              <b>{summary.issueDescription}</b>
              <p>{task.message}</p>
              <small>查看下方 Listing 的原因和可执行操作；已生成的结果仍可查看。</small>
            </div>
          </section>
        )}

        {modelServiceIssue && (
          <div className="task-model-service-alert" role="alert">
            <WarningCircle size={20} weight="fill" />
            <div>
              <b>
                {task.status === "paused" && task.pause_requested
                  ? "模型服务异常，任务已自动暂停"
                  : task.status === "paused"
                    ? "模型服务异常，任务已暂停"
                    : task.status === "failed"
                      ? "模型服务异常，执行已停止"
                      : "模型服务异常，请检查连接与运行日志"}
              </b>
              <span>{modelServiceIssue.error}</span>
            </div>
            <small>
              成功 {modelServiceIssue.model_calls || 0} · 失败{" "}
              {modelServiceIssue.model_failures || 0} · 缓存{" "}
              {modelServiceIssue.cache_hits || 0}
            </small>
          </div>
        )}

        <section className="task-overview-band" aria-label="任务运行总览">
          <div className="task-overview-metrics">
            <div className="primary">
              <span>评论处理进度</span>
              <b>{Math.round(task.progress_percent || 0)}%</b>
              <small>
                {(task.progress_current || 0).toLocaleString()} /{" "}
                {(task.progress_total || 0).toLocaleString()} 组评论
              </small>
            </div>
            <div>
              <span>已生成结果</span>
              <b>
                {summary.generated}
                <small> / {summary.total} 个 Listing</small>
              </b>
              <small>{summary.resultDescription || "分析完成后生成结果"}</small>
            </div>
            <div>
              <span>需要处理</span>
              <b>
                {summary.issues || (summary.needsAttention ? "待确认" : 0)}
                {(!summary.needsAttention || summary.issues > 0) && (
                  <small> 个 Listing</small>
                )}
              </b>
              {summary.needsAttention ? (
                <Button
                  type="link"
                  className="task-inline-action"
                  onClick={() => showListings("attention")}
                >
                  查看需处理事项
                </Button>
              ) : (
                <small>
                  {task.status === "paused"
                    ? "未完成部分已暂停，可随时继续"
                    : "暂无需介入的问题"}
                </small>
              )}
            </div>
          </div>
        </section>

        <div className="task-detail-tabs" role="tablist" aria-label="任务详情视图">
          {DETAIL_TABS.map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="tab"
              id={`task-tab-${value}`}
              aria-controls="task-view-panel"
              aria-selected={activeTab === value}
              className={activeTab === value ? "active" : ""}
              onClick={() => {
                setActiveTab(value);
                if (value === "execution") setListingFilter("all");
              }}
            >
              {label}
            </button>
          ))}
        </div>

        <section
          className="task-detail-tab-panel"
          id="task-view-panel"
          role="tabpanel"
          aria-labelledby={`task-tab-${activeTab}`}
        >
          {activeTab === "execution" && (
            <SegmentBoard
              key={listingFilter}
              initialFilter={listingFilter}
              task={task}
              focusSegmentId={listingFilter === "all" ? focusSegmentId : null}
              onRetry={(segment) => {
                onClearActionError();
                setRetrySegment(segment);
              }}
              onRetryPublish={onRetryResultPublish}
              onCancel={(segment) => setCancelSegment(segment)}
              onAction={onSegmentAction}
              onParallelism={onParallelism}
              onReorder={onReorderSegments}
              onViewClassification={onViewClassification}
              onResumeUnfinished={() => setResumeOpen(true)}
            />
          )}

          {activeTab === "events" && (
            <section className="task-secondary-section full-event-section">
              <header>
                <div>
                  <h3>完整运行日志</h3>
                  <p>来自后台执行器的真实事件，按时间倒序排列。</p>
                </div>
                <span className="live-tag">
                  {isActive && <i />}
                  {isActive ? "实时更新" : "完整记录"}
                </span>
              </header>
              <TaskEventList task={task} events={events} />
            </section>
          )}

          {activeTab === "config" && (
            <section className="task-secondary-section task-config-panel">
              <header>
                <div>
                  <h3>任务配置</h3>
                  <p>任务运行期间始终使用创建时固化的版本。</p>
                </div>
              </header>
              <div className="task-config-body">
                <InfoRow label="分类标准" value={firstStandard?.standard_name || "—"} />
                <InfoRow label="并行数" value={task.max_parallel_segments ?? 3} />
                <InfoRow label="任务 ID" value={task.id} />
                <InfoRow
                  label="退货明细"
                  value={`${task.dataset_name || "—"} · v${task.dataset_version || "—"}`}
                />
                <InfoRow
                  label="产品信息"
                  value={`${task.product_name || "—"} · v${task.product_version || "—"}`}
                />
                <InfoRow
                  label="模型配置"
                  value={`${task.connection_name || "—"} · #${task.config_version || "—"}`}
                />
                <InfoRow
                  label="主模型"
                  value={`${task.primary_model || "—"} · ${
                    (task.primary_effort && EFFORT_LABELS[task.primary_effort]) || "—"
                  }`}
                />
              </div>
            </section>
          )}
        </section>

        {renameOpen && (
          <TaskRenameDialog
            task={task}
            onClose={() => setRenameOpen(false)}
            onSave={async (payload) => {
              const saved = await onRename(payload);
              if (saved) setRenameOpen(false);
            }}
          />
        )}
        {cancelOpen && (
          <TaskCancelDialog
            task={task}
            onClose={() => setCancelOpen(false)}
            onSave={async (payload) => {
              const saved = await onCancel(payload);
              if (saved) setCancelOpen(false);
            }}
          />
        )}
        {resumeOpen && (
          <TaskResumeDialog
            task={task}
            onClose={() => setResumeOpen(false)}
            onSave={async (payload) => {
              const saved = await onResume(payload);
              if (saved) setResumeOpen(false);
            }}
          />
        )}
        {retrySegment && (
          <SegmentRetryDialog
            task={task}
            segment={retrySegment}
            error={actionError}
            onClose={() => setRetrySegment(null)}
            onSave={async (payload) => {
              const saved = await onRetrySegment(retrySegment.segment_key, payload);
              if (saved) setRetrySegment(null);
            }}
          />
        )}
        {cancelSegment && (
          <SegmentCancelDialog
            segment={cancelSegment}
            onClose={() => setCancelSegment(null)}
            onSave={async (note) => {
              const saved = await onSegmentAction(
                cancelSegment.segment_key,
                "cancel",
                note,
              );
              if (saved) setCancelSegment(null);
            }}
          />
        )}
        {replanOpen && (
          <TaskReplanDialog
            task={task}
            onClose={() => setReplanOpen(false)}
            onPreflight={onPreflightReplan}
            onSave={async (payload) => {
              const saved = await onReplan(payload);
              if (saved) setReplanOpen(false);
            }}
          />
        )}
      </>
    </AntdProvider>
  );
}
