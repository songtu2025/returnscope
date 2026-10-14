import { ArrowClockwise, Pause, Play } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { canRetrySegment } from "./segmentBoardRowPolicy";
import { SegmentRemovalControls } from "./SegmentRemovalControls";

/** @typedef {import("./segmentBoardRowContracts").SegmentBoardRowProps} SegmentBoardRowProps */
/** @typedef {Pick<SegmentBoardRowProps, "task" | "segment" | "rowState" | "actions"> & {publishStatus: string}} PrimaryActionsProps */

/** @param {Pick<PrimaryActionsProps, "segment" | "actions">} props */
function SegmentExecutionControls({ segment, actions }) {
  const { onAction } = actions;
  return (
    <>
      {segment.status === "cancelled" && (
        <Button
          className="secondary-button compact-button listing-resume-button"
          onClick={() => onAction(segment.segment_key, "resume")}
        >
          <ArrowClockwise size={14} /> 重新排队
        </Button>
      )}
      {["queued", "retry_pending"].includes(segment.status) && (
        <Button
          className="secondary-button compact-button"
          onClick={() => onAction(segment.segment_key, "pause")}
        >
          <Pause size={14} /> 暂停
        </Button>
      )}
      {segment.status === "running" && !segment.requested_action && (
        <Button
          className="secondary-button compact-button"
          onClick={() => onAction(segment.segment_key, "pause")}
        >
          <Pause size={14} /> 暂停
        </Button>
      )}
      {segment.status === "paused" && (
        <Button
          className="secondary-button compact-button"
          onClick={() => onAction(segment.segment_key, "resume")}
        >
          <Play size={14} /> 继续
        </Button>
      )}
    </>
  );
}

/** @param {Pick<PrimaryActionsProps, "task" | "segment" | "actions">} props */
function SegmentRetryControls({ task, segment, actions }) {
  const { onRetry } = actions;
  const canRetrySystemAnomalies =
    segment.system_retry_available === true &&
    !["queued", "running"].includes(task.status);
  return (
    <>
      {canRetrySystemAnomalies && (
        <Button
          className="secondary-button compact-button"
          title={
            segment.system_failure_count
              ? `重新分析 ${segment.system_failure_count} 个失败项`
              : "重新分析失败项"
          }
          onClick={() => onRetry(segment)}
        >
          <ArrowClockwise size={15} />
          重试失败项
        </Button>
      )}
      {!canRetrySystemAnomalies && canRetrySegment(task, segment) && (
        <Button
          className="secondary-button compact-button"
          onClick={() => onRetry(segment)}
        >
          <ArrowClockwise size={15} />
          重试
        </Button>
      )}
    </>
  );
}

/** @param {PrimaryActionsProps} props */
export function SegmentPrimaryActions({
  task,
  segment,
  rowState,
  actions,
  publishStatus,
}) {
  const unavailable = Boolean(
    segment.deleted_at || segment.removal_requested_at || segment.requested_action,
  );
  const hasExecutionAction = [
    "queued",
    "retry_pending",
    "running",
    "paused",
    "cancelled",
  ].includes(segment.status);
  return (
    <div className="listing-actions" role="cell">
      <div className="listing-control-actions">
        {segment.removal_requested_at ? (
          <span role="status">正在移除…</span>
        ) : (
          <>
            {!unavailable && !segment.result_deleted_at && (
              <SegmentExecutionControls segment={segment} actions={actions} />
            )}
            {!unavailable &&
              !hasExecutionAction &&
              !segment.result_deleted_at &&
              publishStatus !== "failed" && (
                <SegmentRetryControls task={task} segment={segment} actions={actions} />
              )}
            {!unavailable && !hasExecutionAction && publishStatus === "failed" && (
              <Button
                className="secondary-button compact-button"
                disabled={rowState.retryingPublishId === segment.id}
                onClick={async () => {
                  rowState.setRetryingPublishId(segment.id);
                  try {
                    await actions.onRetryPublish(segment.id);
                  } finally {
                    rowState.setRetryingPublishId(null);
                  }
                }}
              >
                {rowState.retryingPublishId === segment.id
                  ? "正在重试"
                  : "重试生成结果"}
              </Button>
            )}
            {!unavailable && (
              <SegmentRemovalControls segment={segment} actions={actions} />
            )}
            {segment.requested_action && !segment.removal_requested_at && (
              <span role="status">正在暂停…</span>
            )}
          </>
        )}
      </div>
    </div>
  );
}
