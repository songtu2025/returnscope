import { useEffect, useRef, useState } from "react";
import { AntdProvider } from "../../components/AntdProvider";
import { SegmentRetryDialog, TaskResumeDialog } from "./TaskActionDialogs";
import { SegmentBoard } from "./SegmentBoard";
import { TaskDetailAlerts } from "./TaskDetailAlerts";
import { TaskDetailHeader } from "./TaskDetailHeader";
import { TaskDetailOverview } from "./TaskDetailOverview";
import { TaskDetailTabs, TaskDetailViews } from "./TaskDetailViews";
import { TaskReplanDialog } from "./TaskReplanDialog";

import { taskSummary } from "./taskRegistryPolicy";
import { publishedTaskResults } from "./taskSegmentPolicy";
import { useTaskLogNavigation } from "./useTaskLogNavigation";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskEvent} TaskEvent */
/** @typedef {import("./taskRuntimeContracts").TaskPayload} TaskPayload */
/** @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment */
/** @typedef {import("./taskRuntimeContracts").SegmentAction} SegmentAction */
/** @typedef {import("../task-planning/taskPlanContracts").TaskExecutionPlan} TaskExecutionPlan */
/**
 * @typedef {Object} TaskDetailProps
 * @property {AnalysisTask} task
 * @property {(disabled: boolean) => import("react").ReactNode} [headerAction]
 * @property {import("./useSegmentBoardView").SegmentBoardReturnRef} [listingReturnState]
 * @property {string | null} [focusSegmentId]
 * @property {TaskEvent[]} events
 * @property {(segment: TaskSegment & {result_version_id: string}, qualityStatus?: string, systemRerunRequired?: string) => void} onViewClassification
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
 * @property {import("./taskSegmentBatchActions").ApplySegmentBatch} [onBatchSegmentAction]
 * @property {() => Promise<boolean>} [onRefreshSegments]
 * @property {(maxParallelSegments: number) => Promise<boolean>} onParallelism
 * @property {(segmentKeys: string[]) => Promise<boolean>} onReorderSegments
 * @property {(payload: TaskPayload) => Promise<TaskExecutionPlan>} onPreflightReplan
 * @property {(payload: TaskPayload) => Promise<boolean>} onReplan
 */

/** @param {TaskDetailProps} props */
export function TaskDetail({
  task,
  headerAction,
  listingReturnState,
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
  onBatchSegmentAction,
  onRefreshSegments,
  onParallelism,
  onReorderSegments,
  onPreflightReplan,
  onReplan,
}) {
  const [resumeOpen, setResumeOpen] = useState(false);
  const [taskAction, setTaskAction] = useState("");
  const [batchReadRequired, setBatchReadRequired] = useState(false);
  const actionRef = useRef("");
  const [taskActionError, setTaskActionError] = useState("");
  const runTaskAction = async (
    /** @type {string} */ action,
    /** @type {() => unknown | Promise<unknown>} */ submit,
  ) => {
    if (actionRef.current) return false;
    actionRef.current = action;
    setTaskAction(action);
    setTaskActionError("");
    try {
      return await submit();
    } catch (failure) {
      setTaskActionError(
        failure instanceof Error ? failure.message : "任务操作失败，请重试",
      );
      return false;
    } finally {
      actionRef.current = "";
      setTaskAction("");
    }
  };
  const [retrySegment, setRetrySegment] = useState(
    /** @type {TaskSegment | null} */ (null),
  );
  const [replanOpen, setReplanOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("execution");
  const logs = useTaskLogNavigation(setActiveTab);
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
  const viewResults = () => {
    const results = publishedTaskResults(task);
    if (results.length === 1) onViewClassification(results[0]);
    else {
      showListings("delivered");
      requestAnimationFrame(() => {
        const panel = document.getElementById("task-view-panel");
        panel?.scrollIntoView({ block: "start" });
        panel?.focus({ preventScroll: true });
      });
    }
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
          headerAction={headerAction}
          summary={summary}
          hasUnfinishedSegments={hasUnfinishedSegments}
          taskAction={taskAction || (batchReadRequired ? "read-required" : "")}
          onOpenReplan={() => setReplanOpen(true)}
          onOpenResume={() => setResumeOpen(true)}
          onTaskRenamed={onTaskRenamed}
          onPause={() => runTaskAction("pause", onPause)}
          onRetry={() => runTaskAction("retry", onRetry)}
          onArchive={() => runTaskAction("archive", onArchive)}
          onViewResults={viewResults}
        />

        <TaskDetailAlerts
          task={task}
          summary={summary}
          actionError={taskActionError || actionError}
          retrySegment={retrySegment}
          modelServiceIssue={modelServiceIssue}
          onClearActionError={() => {
            setTaskActionError("");
            onClearActionError();
          }}
        />

        <TaskDetailOverview task={task} summary={summary} showListings={showListings} />

        <TaskDetailTabs
          activeTab={activeTab}
          disabled={Boolean(taskAction)}
          onSelect={(value) => {
            setActiveTab(value);
          }}
        />

        <TaskDetailViews
          task={task}
          events={events}
          executableSegments={executableSegments}
          activeTab={activeTab}
          focusListing={logs.listing}
          execution={
            <SegmentBoard
              key={listingFilter}
              initialFilter={listingFilter}
              returnState={listingReturnState}
              task={task}
              disabled={Boolean(taskAction)}
              readRequired={batchReadRequired}
              focusSegmentId={listingFilter === "all" ? focusSegmentId : null}
              onRetry={(segment) => {
                onClearActionError();
                setRetrySegment(segment);
              }}
              onRetryPublish={(id) =>
                runTaskAction("publish", () => onRetryResultPublish(id))
              }
              onAction={(key, action, note) =>
                runTaskAction("segment", () => onSegmentAction(key, action, note))
              }
              onBatchAction={
                onBatchSegmentAction
                  ? async (keys, action) => {
                      if (batchReadRequired) return false;
                      const result = await runTaskAction("batch-segment", () =>
                        onBatchSegmentAction(keys, action),
                      );
                      if (
                        result &&
                        typeof result === "object" &&
                        "refreshRequired" in result
                      )
                        setBatchReadRequired(Boolean(result.refreshRequired));
                      return /** @type {import("./taskSegmentBatchActions").SegmentBatchResult | false} */ (
                        result
                      );
                    }
                  : undefined
              }
              onRefresh={
                onRefreshSegments
                  ? async () => {
                      const read = Boolean(
                        await runTaskAction("refresh-segments", onRefreshSegments),
                      );
                      if (read) setBatchReadRequired(false);
                      return read;
                    }
                  : undefined
              }
              onParallelism={(value) =>
                runTaskAction("parallelism", () => onParallelism(value))
              }
              onReorder={(keys) =>
                runTaskAction("order", () => onReorderSegments(keys))
              }
              onViewClassification={onViewClassification}
              onViewLogs={logs.open}
            />
          }
        />

        {resumeOpen && (
          <TaskResumeDialog
            task={task}
            onClose={() => setResumeOpen(false)}
            onSave={async (payload) => {
              const saved = await runTaskAction("resume", () => onResume(payload));
              if (saved) setResumeOpen(false);
            }}
          />
        )}
        {retrySegment && (
          <SegmentRetryDialog
            task={task}
            segment={retrySegment}
            error={taskActionError || actionError}
            onClose={() => {
              if (!actionRef.current) setRetrySegment(null);
            }}
            onSave={async (payload) => {
              const saved = await runTaskAction("retry-segment", () =>
                onRetrySegment(retrySegment.segment_key, payload),
              );
              if (saved) setRetrySegment(null);
            }}
          />
        )}
        {replanOpen && (
          <TaskReplanDialog
            task={task}
            onClose={() => {
              if (!actionRef.current) setReplanOpen(false);
            }}
            onPreflight={onPreflightReplan}
            onSave={async (payload) => {
              const saved = await runTaskAction("replan", () => onReplan(payload));
              if (saved) setReplanOpen(false);
            }}
          />
        )}
      </>
    </AntdProvider>
  );
}
