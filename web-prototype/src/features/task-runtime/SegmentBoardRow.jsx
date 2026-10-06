import { ArrowClockwise, ChartBar, Pause, Play } from "@phosphor-icons/react";
import Button from "antd/es/button";

import { classNames } from "../../lib/presentation";
import { isLegacyResult, isPublishedResult, moveSegmentKey } from "./taskSegmentPolicy";
import { SegmentBoardDetail } from "./SegmentBoardDetail";
import {
  canRetrySegment,
  segmentResultPresentation,
  SEGMENT_STATUS_LABELS,
} from "./segmentBoardRowPolicy";
import { segmentNeedsAttention } from "./taskRegistryPolicy";

/** @typedef {import("./segmentBoardRowContracts").SegmentBoardRowProps} SegmentBoardRowProps */

/** @param {SegmentBoardRowProps} props */
export function SegmentBoardRow({ task, segment, position, queue, rowState, actions }) {
  const { segmentIndex, page, pageSize, focusSegmentId, focusedSegmentRef } = position;
  const { canManageQueue, orderableKeys, reordering, applyOrder } = queue;
  const {
    expandedSegmentKey,
    setExpandedSegmentKey,
    retryingPublishId,
    setRetryingPublishId,
  } = rowState;
  const {
    onResumeUnfinished,
    onAction,
    onRetry,
    onViewClassification,
    onRetryPublish,
  } = actions;
  const isFocused =
    Boolean(focusSegmentId) &&
    [segment.id, segment.segment_key].some(
      (value) => String(value) === String(focusSegmentId),
    );
  const progress = segment.progress_total
    ? Math.round((segment.progress_current / segment.progress_total) * 100)
    : 0;
  const orderableIndex = orderableKeys.indexOf(segment.segment_key);
  const canOrder = canManageQueue && orderableIndex >= 0 && orderableKeys.length > 1;
  const canRetrySystemAnomalies =
    segment.system_retry_available === true &&
    !["queued", "running"].includes(task.status);
  const { displayStatus, publishStatus, qualityState, stateLabel, stateDescription } =
    segmentResultPresentation(segment);

  return (
    <article
      ref={isFocused ? focusedSegmentRef : null}
      draggable={canOrder && !reordering && expandedSegmentKey === segment.segment_key}
      onDragStart={(event) => {
        event.dataTransfer.setData("text/plain", segment.segment_key);
        event.dataTransfer.effectAllowed = "move";
      }}
      onDragOver={(event) => {
        if (canOrder) event.preventDefault();
      }}
      onDrop={(event) => {
        if (!canOrder) return;
        event.preventDefault();
        const sourceKey = event.dataTransfer.getData("text/plain");
        applyOrder(moveSegmentKey(orderableKeys, sourceKey, orderableIndex));
      }}
      className={classNames(
        "listing-row",
        segment.error && "has-error",
        canOrder && "is-orderable",
        isFocused && "is-targeted",
      )}
      aria-current={isFocused ? "true" : undefined}
      role="row"
    >
      <div className="listing-identity" role="cell">
        <b>
          {String(
            segment.execution_order || (page - 1) * pageSize + segmentIndex + 1,
          ).padStart(2, "0")}
        </b>
        <div>
          <h4>{segment.scope?.listing || "未匹配 Listing"}</h4>
          <p>{segment.scope?.store || task.store}</p>
        </div>
      </div>
      <div className="listing-agent" role="cell">
        <b>{segment.standard_name || segment.agent_family}</b>
        <p>
          {segment.variants
            ?.map((variant) => variant.category_b || "缺失品类B")
            .join("、")}
        </p>
      </div>
      <div className="listing-state" role="cell">
        <span className={`segment-status ${displayStatus}`}>
          {SEGMENT_STATUS_LABELS[displayStatus] ?? displayStatus}
        </span>
        {segment.wait_reason && <small>{segment.wait_reason}</small>}
      </div>
      <div className="listing-result" role="cell">
        <span
          className={`segment-status ${publishStatus === "published" ? qualityState : publishStatus || "pending"}`}
        >
          {publishStatus || isLegacyResult(segment)
            ? isLegacyResult(segment)
              ? "旧结果 · 质量未确认"
              : stateLabel
            : "未生成"}
        </span>
        {publishStatus === "failed" && (
          <small className="result-publish-error">{stateDescription}</small>
        )}
      </div>
      <div className="listing-progress-cell" role="cell">
        <b>{progress}%</b>
        <span>
          {segment.progress_current} / {segment.progress_total}
        </span>
        <div className="segment-progress" aria-label={`Listing 进度 ${progress}%`}>
          <span style={{ width: `${progress}%` }} />
        </div>
        <small>{segment.record_count.toLocaleString()} 条记录</small>
      </div>
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
      {segment.error && segmentNeedsAttention(segment) && (
        <p className="segment-error">{segment.error}</p>
      )}
      {expandedSegmentKey === segment.segment_key && (
        <SegmentBoardDetail
          task={task}
          segment={segment}
          canOrder={canOrder}
          orderableIndex={orderableIndex}
          queue={queue}
          actions={actions}
          stateDescription={stateDescription}
          stateLabel={stateLabel}
        />
      )}
    </article>
  );
}
