import { useEffect, useState } from "react";
import { AntdProvider } from "../../components/AntdProvider";
import { SegmentRetryDialog, TaskResumeDialog } from "./TaskActionDialogs";
import { SegmentBoard } from "./SegmentBoard";
import { TaskDetailAlerts } from "./TaskDetailAlerts";
import { TaskDetailHeader } from "./TaskDetailHeader";
import { TaskDetailOverview } from "./TaskDetailOverview";
import { TaskDetailViews } from "./TaskDetailViews";
import { TaskReplanDialog } from "./TaskReplanDialog";

import { taskSummary } from "./taskRegistryPolicy";

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
 * @property {(segment: TaskSegment & {result_version_id: string}, qualityStatus?: string) => void} onViewClassification
 * @property {string} actionError
 * @property {() => void} onClearActionError
 * @property {(task: AnalysisTask) => Promise<unknown>} onTaskRenamed
 * @property {() => void | Promise<unknown>} onArchive
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
  onTaskRenamed,
  onArchive,
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
  const [resumeOpen, setResumeOpen] = useState(false);
  const [retrySegment, setRetrySegment] = useState(
    /** @type {TaskSegment | null} */ (null),
  );
  const [replanOpen, setReplanOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("execution");
  const [listingFilter, setListingFilter] = useState("all");
  const summary = taskSummary(task);
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
  const hasUnfinishedSegments = task.segments?.some(
    (segment) =>
      !segment.deleted_at &&
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
    task.segments?.filter(
      (segment) => segment.agent_key !== "unknown" && !segment.deleted_at,
    ) ?? [];
  const modelServiceIssue = executableSegments.find(
    (segment) =>
      ["paused", "failed", "running"].includes(segment.status) &&
      Number(segment.model_failures || 0) >= 3 &&
      segment.error,
  );

  return (
    <AntdProvider>
      <>
        <TaskDetailHeader
          task={task}
          summary={summary}
          hasUnfinishedSegments={hasUnfinishedSegments}
          onOpenReplan={() => setReplanOpen(true)}
          onOpenResume={() => setResumeOpen(true)}
          onTaskRenamed={onTaskRenamed}
          onPause={onPause}
          onRetry={onRetry}
          onArchive={onArchive}
          showListings={showListings}
        />

        <TaskDetailAlerts
          task={task}
          summary={summary}
          actionError={actionError}
          retrySegment={retrySegment}
          modelServiceIssue={modelServiceIssue}
          onClearActionError={onClearActionError}
        />

        <TaskDetailOverview task={task} summary={summary} showListings={showListings} />

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

        <TaskDetailViews
          task={task}
          events={events}
          executableSegments={executableSegments}
          activeTab={activeTab}
          execution={
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
              onAction={onSegmentAction}
              onParallelism={onParallelism}
              onReorder={onReorderSegments}
              onViewClassification={onViewClassification}
            />
          }
        />

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
