import { useEffect, useRef, useState } from "react";
import {
  ArrowClockwise,
  ArrowDown,
  ArrowLineUp,
  ArrowUp,
  ChartBar,
  DownloadSimple,
  Pause,
  Play,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { api } from "../../api";
import { CardHeading } from "../../components/SharedUi";
import {
  resultState,
  resultStateLabel,
} from "../classification-results/resultActionPolicy";
import { classNames } from "../../lib/presentation";
import {
  isLegacyResult,
  isPublishedResult,
  moveSegmentKey,
  resultPublishStatus,
} from "./taskSegmentPolicy";

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
const ORDERABLE_SEGMENT_STATUSES = ["queued", "retry_pending", "paused"];

function shortPublishError(value) {
  const message = String(value || "未返回具体原因")
    .replace(/\s+/g, " ")
    .trim();
  return message.length > 80 ? `${message.slice(0, 80)}…` : message;
}

function canRetrySegment(task, segment) {
  if (["queued", "running"].includes(task.status)) return false;
  if (segment.agent_key === "unknown" || segment.status === "blocked") return false;
  if (!RETRYABLE_SEGMENT_STATUSES.includes(segment.status)) return false;
  const blockedExists = task.segments?.some((item) => item.status === "blocked");
  const policy = task.snapshot?.execution_plan?.unresolved_policy ?? "block_all";
  return !(segment.status === "not_started" && policy === "block_all" && blockedExists);
}

export function SegmentBoard({
  task,
  focusSegmentId,
  onRetry,
  onRetryPublish,
  onCancel,
  onAction,
  onParallelism,
  onReorder,
  onViewClassification,
}) {
  const [reordering, setReordering] = useState(false);
  const [changingParallelism, setChangingParallelism] = useState(false);
  const [retryingPublishId, setRetryingPublishId] = useState(null);
  const focusedSegmentRef = useRef(null);

  useEffect(() => {
    if (!focusSegmentId || !focusedSegmentRef.current) return;
    focusedSegmentRef.current.scrollIntoView({ block: "center" });
  }, [focusSegmentId, task.segments]);

  if (!task.segments?.length) return null;
  const queueSegments = task.segments.filter(
    (segment) => segment.agent_key !== "unknown",
  );
  const excludedSegments = task.segments.filter(
    (segment) => segment.agent_key === "unknown",
  );
  const excludedRecords = excludedSegments.reduce(
    (total, segment) => total + segment.record_count,
    0,
  );
  const excludedComments = excludedSegments.reduce(
    (total, segment) => total + segment.unique_comments,
    0,
  );
  const maxParallelSegments = task.max_parallel_segments ?? 3;
  const ownerRunningSegments = task.owner_running_segments ?? 0;
  const canManageQueue = ["queued", "running", "paused"].includes(task.status);
  const orderableKeys = queueSegments
    .filter((segment) => ORDERABLE_SEGMENT_STATUSES.includes(segment.status))
    .map((segment) => segment.segment_key);

  const applyOrder = async (segmentKeys) => {
    if (reordering || !onReorder || segmentKeys.join("|") === orderableKeys.join("|")) {
      return;
    }
    setReordering(true);
    await onReorder(segmentKeys);
    setReordering(false);
  };

  return (
    <section className="segment-board listing-queue" aria-label="Listing 执行队列">
      <div className="listing-queue-header">
        <CardHeading
          title="Listing 执行队列"
          note="每个 Listing 独立排队、运行和交付；智能体是执行策略，不占并发名额"
        />
        <div className="parallelism-control" aria-label="Listing 并行数">
          <span>我的运行片段</span>
          <b>
            {ownerRunningSegments}/{task.owner_segment_limit ?? 3}
          </b>
          <span className="parallelism-divider" />
          <span>本批量并行</span>
          <button
            type="button"
            className="icon-button"
            disabled={
              changingParallelism || !canManageQueue || maxParallelSegments <= 1
            }
            aria-label="减少 Listing 并行数"
            onClick={async () => {
              setChangingParallelism(true);
              await onParallelism(maxParallelSegments - 1);
              setChangingParallelism(false);
            }}
          >
            −
          </button>
          <b>{maxParallelSegments}</b>
          <button
            type="button"
            className="icon-button"
            disabled={
              changingParallelism || !canManageQueue || maxParallelSegments >= 3
            }
            aria-label="增加 Listing 并行数"
            onClick={async () => {
              setChangingParallelism(true);
              await onParallelism(maxParallelSegments + 1);
              setChangingParallelism(false);
            }}
          >
            +
          </button>
        </div>
      </div>
      {queueSegments.length > 0 && (
        <>
          <p className="horizontal-scroll-hint">
            窗口较窄时可横向滚动查看模型信息与操作。
          </p>
          <div className="listing-table" role="table">
            <div className="listing-table-head" role="row">
              <span>顺序 / Listing</span>
              <span>品类与智能体</span>
              <span>状态</span>
              <span>进度</span>
              <span>模型</span>
              <span>操作</span>
            </div>
            {queueSegments.map((segment, segmentIndex) => {
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
              const canOrder =
                canManageQueue && orderableIndex >= 0 && orderableKeys.length > 1;
              const segmentLabel = segment.scope?.listing || segment.agent_family;
              const displayStatus = segment.display_status || segment.status;
              const publishStatus = resultPublishStatus(segment);
              const stateStatus = ["publishing", "published", "failed"].includes(
                publishStatus,
              )
                ? publishStatus
                : displayStatus;
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
                  ? "分类完成，正在发布不可变结果版本"
                  : publishStatus === "failed"
                    ? shortPublishError(segment.result_publish_error)
                    : publishStatus === "published"
                      ? "版本发布：已发布"
                      : segment.wait_reason;
              return (
                <article
                  key={segment.segment_key}
                  ref={isFocused ? focusedSegmentRef : null}
                  draggable={canOrder && !reordering}
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
                    applyOrder(
                      moveSegmentKey(orderableKeys, sourceKey, orderableIndex),
                    );
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
                      {String(segment.execution_order || segmentIndex + 1).padStart(
                        2,
                        "0",
                      )}
                    </b>
                    <div>
                      <h4>{segment.scope?.listing || "未匹配 Listing"}</h4>
                      <p>{segment.scope?.store || task.store}</p>
                    </div>
                  </div>
                  <div className="listing-agent" role="cell">
                    <b>{segment.agent_family}</b>
                    <p>
                      {segment.variants
                        ?.map((variant) => variant.category_b || "缺失品类B")
                        .join("、")}
                    </p>
                    <small>{segment.logic_version || "未配置逻辑"}</small>
                  </div>
                  <div className="listing-state" role="cell">
                    <span
                      className={`segment-status ${
                        publishStatus === "published" ? qualityState : stateStatus
                      }`}
                    >
                      {stateLabel}
                    </span>
                    {stateDescription && (
                      <small
                        className={
                          publishStatus === "failed" ? "result-publish-error" : ""
                        }
                      >
                        {stateDescription}
                      </small>
                    )}
                  </div>
                  <div className="listing-progress-cell" role="cell">
                    <b>{progress}%</b>
                    <span>
                      {segment.progress_current} / {segment.progress_total}
                    </span>
                    <div
                      className="segment-progress"
                      aria-label={`Listing 进度 ${progress}%`}
                    >
                      <span style={{ width: `${progress}%` }} />
                    </div>
                    <small>{segment.record_count.toLocaleString()} 条记录</small>
                  </div>
                  <div className="listing-model" role="cell">
                    <b>{modelRequests} 次请求</b>
                    <span>
                      成功 {segment.model_calls || 0} · 失败 {modelFailures}
                    </span>
                    <small>
                      缓存 {segment.cache_hits || 0} · {segment.taxonomy_version}
                    </small>
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
                      {canOrder && (
                        <div
                          className="listing-order-actions"
                          aria-label="调整执行顺序"
                        >
                          <button
                            type="button"
                            className="icon-button"
                            aria-label={`置顶 ${segmentLabel}`}
                            title="置顶"
                            disabled={reordering || orderableIndex === 0}
                            onClick={() =>
                              applyOrder(
                                moveSegmentKey(orderableKeys, segment.segment_key, 0),
                              )
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
                            disabled={
                              reordering || orderableIndex === orderableKeys.length - 1
                            }
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
                      <div className="listing-control-actions">
                        {["queued", "retry_pending"].includes(segment.status) && (
                          <button
                            className="secondary-button compact-button"
                            onClick={() => onAction(segment.segment_key, "pause")}
                          >
                            <Pause size={14} /> 暂停
                          </button>
                        )}
                        {segment.status === "running" && !segment.requested_action && (
                          <button
                            className="secondary-button compact-button"
                            onClick={() => onAction(segment.segment_key, "pause")}
                          >
                            <Pause size={14} /> 暂停
                          </button>
                        )}
                        {segment.status === "paused" && (
                          <button
                            className="secondary-button compact-button"
                            onClick={() => onAction(segment.segment_key, "resume")}
                          >
                            <Play size={14} /> 继续
                          </button>
                        )}
                        {canRetrySegment(task, segment) && (
                          <button
                            className="secondary-button compact-button"
                            onClick={() => onRetry(segment)}
                          >
                            <ArrowClockwise size={15} />
                            重试
                          </button>
                        )}
                        {[
                          "queued",
                          "retry_pending",
                          "running",
                          "paused",
                          "failed",
                        ].includes(segment.status) && (
                          <button
                            className="secondary-button compact-button listing-cancel-button"
                            onClick={() => onCancel(segment)}
                          >
                            <X size={14} /> 取消
                          </button>
                        )}
                        {publishStatus === "publishing" && (
                          <>
                            <button
                              className="secondary-button compact-button"
                              disabled
                              title="结果发布完成后即可查看"
                            >
                              <ChartBar size={14} /> 查看分类结果
                            </button>
                            <button
                              className="secondary-button compact-button"
                              disabled
                              title="结果发布完成后即可下载"
                            >
                              <DownloadSimple size={14} /> 下载
                            </button>
                          </>
                        )}
                        {["completed", "completed_with_errors"].includes(
                          segment.status,
                        ) &&
                          isPublishedResult(segment) && (
                            <button
                              className="secondary-button compact-button listing-view-button"
                              onClick={() => onViewClassification(segment)}
                            >
                              <ChartBar size={14} /> 查看分类结果
                            </button>
                          )}
                        {["completed", "completed_with_errors"].includes(
                          segment.status,
                        ) &&
                          isPublishedResult(segment) && (
                            <a
                              className="secondary-button compact-button"
                              href={api.classificationResultDownloadUrl(
                                segment.result_version_id,
                              )}
                            >
                              <DownloadSimple size={14} /> 下载
                            </a>
                          )}
                        {["completed", "completed_with_errors"].includes(
                          segment.status,
                        ) &&
                          isLegacyResult(segment) && (
                            <a
                              className="secondary-button compact-button"
                              href={api.segmentDownloadUrl(
                                task.id,
                                segment.segment_key,
                              )}
                            >
                              <DownloadSimple size={14} /> 下载旧结果
                            </a>
                          )}
                        {publishStatus === "failed" && (
                          <button
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
                            {retryingPublishId === segment.id
                              ? "正在重试"
                              : "重试生成结果"}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                  {segment.error && <p className="segment-error">{segment.error}</p>}
                </article>
              );
            })}
          </div>
        </>
      )}
      {excludedSegments.length > 0 && (
        <div className="excluded-listing-summary">
          <WarningCircle size={18} />
          <div>
            <b>未配置品类的数据未纳入语义分析</b>
            <p>
              {excludedRecords.toLocaleString()} 条记录 /{" "}
              {excludedComments.toLocaleString()}
              组评论，不创建 Listing 执行项，也不会调用模型。
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
