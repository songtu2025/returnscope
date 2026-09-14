import {
  ArrowClockwise,
  ArrowDown,
  ArrowLineUp,
  ArrowUp,
  ChartBar,
  DownloadSimple,
  Pause,
  Play,
  X,
} from "@phosphor-icons/react";
import Button from "antd/es/button";

import { api } from "../../api";
import { classNames, formatTime } from "../../lib/presentation";
import {
  resultState,
  resultStateLabel,
} from "../classification-results/resultActionPolicy";
import {
  isLegacyResult,
  isPublishedResult,
  moveSegmentKey,
  resultPublishStatus,
} from "./taskSegmentPolicy";
import { segmentNeedsAttention } from "./taskRegistryPolicy";

const RETRYABLE_SEGMENT_STATUSES = ["failed", "completed_with_errors", "not_started"];
const SEGMENT_STATUS_LABELS = {
  ready: "可执行",
  queued: "等待",
  running: "运行中",
  pause_pending: "正在暂停",
  cancel_pending: "正在取消",
  paused: "已暂停",
  completed: "已完成",
  completed_with_errors: "完成但有异常",
  failed: "失败",
  blocked: "未纳入分析",
  cancelled: "已取消",
  not_started: "尚未运行",
  retry_pending: "等待重试",
};

function shortPublishError(value) {
  const message = String(value || "未返回具体原因")
    .replace(/\s+/g, " ")
    .trim();
  return message.length > 80 ? `${message.slice(0, 80)}…` : message;
}

function canRetrySegment(task, segment) {
  if (["queued", "running"].includes(task.status)) return false;
  if (segment.agent_key === "unknown" || segment.status === "blocked") return false;
  if (isPublishedResult(segment)) return false;
  if (!RETRYABLE_SEGMENT_STATUSES.includes(segment.status)) return false;
  const blockedExists = task.segments?.some((item) => item.status === "blocked");
  const policy = task.snapshot?.execution_plan?.unresolved_policy ?? "block_all";
  return !(segment.status === "not_started" && policy === "block_all" && blockedExists);
}

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
    onCancel,
  } = actions;
  const isFocused =
    Boolean(focusSegmentId) &&
    [segment.id, segment.segment_key].some(
      (value) => String(value) === String(focusSegmentId),
    );
  const progress = segment.progress_total
    ? Math.round((segment.progress_current / segment.progress_total) * 100)
    : 0;
  const modelFailures = Number(segment.model_failures || 0);
  const modelRequests = Number(segment.model_calls || 0) + modelFailures;
  const orderableIndex = orderableKeys.indexOf(segment.segment_key);
  const canOrder = canManageQueue && orderableIndex >= 0 && orderableKeys.length > 1;
  const segmentLabel = segment.scope?.listing || segment.agent_family;
  const displayStatus = segment.display_status || segment.status;
  const publishStatus = resultPublishStatus(segment);
  const qualityResult = {
    result_state: segment.result_state,
    result_quality_status: segment.result_quality_status,
    source_review_batch_id: segment.source_review_batch_id,
    publish_status: publishStatus,
  };
  const qualityState = resultState(qualityResult);
  const qualityLabel = resultStateLabel(qualityResult);
  const stateLabel =
    publishStatus === "publishing"
      ? "正在生成结果"
      : publishStatus === "failed"
        ? "结果生成失败"
        : publishStatus === "published"
          ? qualityLabel
          : (SEGMENT_STATUS_LABELS[displayStatus] ?? displayStatus);
  const stateDescription =
    publishStatus === "publishing"
      ? "分类已完成，正在生成结果"
      : publishStatus === "failed"
        ? shortPublishError(segment.result_publish_error)
        : publishStatus === "published"
          ? "结果已生成"
          : segment.wait_reason;

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
            {canRetrySegment(task, segment) && (
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
        <div className="listing-row-detail" role="cell">
          <div className="listing-model">
            <b>{modelRequests} 次请求</b>
            <span>
              成功 {segment.model_calls || 0} · 失败 {modelFailures}
            </span>
            <small>
              缓存 {segment.cache_hits || 0} · {segment.taxonomy_version}
            </small>
          </div>
          <div className="listing-updated">
            <b>
              {formatTime(segment.updated_at || task.updated_at || task.created_at)}
            </b>
            <small>{task.owner_name || "—"}</small>
          </div>
          <div>
            <span>标准版本</span>{" "}
            <small>
              {segment.standard_version ? `标准 V${segment.standard_version} · ` : ""}
              {segment.logic_version || "未配置逻辑"}
            </small>
          </div>
          <div>
            <span>记录与评论</span>
            <b>
              {(segment.record_count || 0).toLocaleString()} 条记录 ·{" "}
              {(segment.unique_comments || 0).toLocaleString()} 组评论
            </b>
          </div>
          <div>
            <span>执行逻辑</span>
            <b>{segment.logic_version || "未配置"}</b>
          </div>
          <div>
            <span>分类版本</span>
            <b>{segment.taxonomy_version || "未生成"}</b>
          </div>
          <div>
            <span>状态说明</span>
            <b>{stateDescription || segment.error || stateLabel}</b>
          </div>
          <div className="listing-secondary-actions">
            {canOrder && (
              <div className="listing-order-actions" aria-label="调整执行顺序">
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`置顶 ${segmentLabel}`}
                  title="置顶"
                  disabled={reordering || orderableIndex === 0}
                  onClick={() =>
                    applyOrder(moveSegmentKey(orderableKeys, segment.segment_key, 0))
                  }
                >
                  <ArrowLineUp size={15} />
                </button>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`上移 ${segmentLabel}`}
                  title="上移"
                  disabled={reordering || orderableIndex === 0}
                  onClick={() =>
                    applyOrder(
                      moveSegmentKey(
                        orderableKeys,
                        segment.segment_key,
                        orderableIndex - 1,
                      ),
                    )
                  }
                >
                  <ArrowUp size={15} />
                </button>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`下移 ${segmentLabel}`}
                  title="下移"
                  disabled={reordering || orderableIndex === orderableKeys.length - 1}
                  onClick={() =>
                    applyOrder(
                      moveSegmentKey(
                        orderableKeys,
                        segment.segment_key,
                        orderableIndex + 1,
                      ),
                    )
                  }
                >
                  <ArrowDown size={15} />
                </button>
              </div>
            )}
            {["queued", "retry_pending", "running", "paused", "failed"].includes(
              segment.status,
            ) && (
              <Button
                className="secondary-button compact-button listing-cancel-button"
                onClick={() => onCancel(segment)}
              >
                <X size={14} /> 取消
              </Button>
            )}
            {["completed", "completed_with_errors"].includes(segment.status) &&
              isPublishedResult(segment) && (
                <a
                  className="secondary-button compact-button"
                  href={api.classificationResultDownloadUrl(segment.result_version_id)}
                >
                  <DownloadSimple size={14} /> 下载
                </a>
              )}
            {["completed", "completed_with_errors"].includes(segment.status) &&
              isLegacyResult(segment) && (
                <a
                  className="secondary-button compact-button"
                  href={api.segmentDownloadUrl(task.id, segment.segment_key)}
                >
                  <DownloadSimple size={14} /> 下载旧结果
                </a>
              )}
          </div>
        </div>
      )}
    </article>
  );
}
