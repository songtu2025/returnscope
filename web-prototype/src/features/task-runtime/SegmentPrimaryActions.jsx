import { ArrowClockwise, ChartBar, Pause, Play } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { isPublishedResult } from "./taskSegmentPolicy";
import { canRetrySegment } from "./segmentBoardRowPolicy";

/** @typedef {import("./segmentBoardRowContracts").SegmentBoardRowProps} SegmentBoardRowProps */
/** @typedef {Pick<SegmentBoardRowProps, "task" | "segment" | "rowState" | "actions"> & {publishStatus: string}} PrimaryActionsProps */

/** @param {Pick<PrimaryActionsProps, "task" | "segment" | "actions">} props */
function SegmentExecutionControls({ task, segment, actions }) {
  const { onResumeUnfinished, onAction } = actions;
  return (
    <>
      {task.status === "cancelled" &&
        ["cancelled", "not_started", "paused"].includes(segment.status) && (
          <Button
            className="secondary-button compact-button listing-resume-button"
            onClick={onResumeUnfinished}
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
              ? `重新处理 ${segment.system_failure_count} 个系统异常`
              : "重新处理系统异常"
          }
          onClick={() => onRetry(segment)}
        >
          <ArrowClockwise size={15} />
          重试系统异常
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

/** @param {Pick<PrimaryActionsProps, "segment" | "rowState" | "actions" | "publishStatus">} props */
function SegmentResultControls({ segment, rowState, actions, publishStatus }) {
  const { retryingPublishId, setRetryingPublishId } = rowState;
  const { onViewClassification, onRetryPublish } = actions;
  return (
    <>
      {["completed", "completed_with_errors"].includes(segment.status) &&
        isPublishedResult(segment) && (
          <Button
            className="secondary-button compact-button listing-view-button"
            onClick={() => onViewClassification(segment)}
          >
            <ChartBar size={14} /> 查看分类结果
          </Button>
        )}
      {publishStatus === "failed" && (
        <Button
          className="secondary-button compact-button"
          disabled={retryingPublishId === segment.id}
          title="只重新发布现有分类结果，不会重新执行语义分类"
          onClick={async () => {
            setRetryingPublishId(segment.id);
            await onRetryPublish(segment.id);
            setRetryingPublishId(null);
          }}
        >
          <ArrowClockwise size={14} />
          {retryingPublishId === segment.id ? "正在重试" : "重试生成结果"}
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
  const { expandedSegmentKey, setExpandedSegmentKey } = rowState;
  return (
    <div
      className="listing-actions"
      role="cell"
      onDragStart={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
    >
      <div className="listing-action-groups">
        <div className="listing-control-actions">
          <SegmentExecutionControls task={task} segment={segment} actions={actions} />
          <SegmentRetryControls task={task} segment={segment} actions={actions} />
          <SegmentResultControls
            segment={segment}
            rowState={rowState}
            actions={actions}
            publishStatus={publishStatus}
          />
          <button
            className="secondary-button compact-button listing-detail-button"
            aria-expanded={expandedSegmentKey === segment.segment_key}
            onClick={() =>
              setExpandedSegmentKey((current) =>
                current === segment.segment_key ? null : segment.segment_key,
              )
            }
          >
            {expandedSegmentKey === segment.segment_key ? "收起详情" : "查看详情"}
          </button>
        </div>
      </div>
    </div>
  );
}
