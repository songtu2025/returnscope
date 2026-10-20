import { ResultDownloadButton } from "../classification-results/ResultDownloadButton";
import { ArrowLineUp, ArrowUp, ArrowDown, DownloadSimple } from "@phosphor-icons/react";
import { api } from "../../api";
import { formatTime } from "../../lib/presentation";
import { isPublishedResult, isLegacyResult, moveSegmentKey } from "./taskSegmentPolicy";

/** @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment */
/** @typedef {Pick<import("./segmentBoardRowContracts").SegmentBoardRowProps, "task" | "segment" | "queue"> & {canOrder: boolean, orderableIndex: number, stateLabel: string, stateDescription: string | undefined, onViewLogs?: (segment: TaskSegment) => void}} SegmentDetailProps */

/** @param {{segment: TaskSegment}} props */
function SegmentModelMetrics({ segment }) {
  const modelFailures = Number(segment.model_failures || 0);
  const modelRequests = Number(segment.model_calls || 0) + modelFailures;
  return (
    <div className="listing-model">
      <b>{modelRequests} 次请求</b>
      <span>
        成功 {segment.model_calls || 0} · 失败 {modelFailures}
      </span>
      <small>缓存 {segment.cache_hits || 0}</small>
    </div>
  );
}

/** @param {Pick<SegmentDetailProps, "task" | "segment" | "stateLabel" | "stateDescription">} props */
function SegmentDetailFacts({ task, segment, stateLabel, stateDescription }) {
  return (
    <>
      <div className="listing-updated">
        <b>{formatTime(segment.updated_at || task.updated_at || task.created_at)}</b>
        <small>{task.owner_name || "—"}</small>
      </div>
      <div>
        <span>记录与评论</span>
        <b>
          {(segment.record_count || 0).toLocaleString()} 条记录 ·{" "}
          {(segment.unique_comments || 0).toLocaleString()} 组评论
        </b>
      </div>
      <div>
        <span>状态说明</span>
        <b>{stateDescription || segment.error || stateLabel}</b>
      </div>
    </>
  );
}

/** @param {{segment: TaskSegment}} props */
function SegmentRunConfiguration({ segment }) {
  return (
    <details className="listing-run-configuration">
      <summary>运行配置</summary>
      <dl>
        <div>
          <dt>标准记录</dt>
          <dd>
            {segment.standard_version
              ? `第 ${segment.standard_version} 次更新`
              : "未记录"}
          </dd>
        </div>
        <div>
          <dt>执行逻辑</dt>
          <dd>{segment.logic_version || "未配置"}</dd>
        </div>
        <div>
          <dt>标签体系编号</dt>
          <dd>{segment.taxonomy_version || "未记录"}</dd>
        </div>
      </dl>
    </details>
  );
}

/** @param {Pick<SegmentDetailProps, "segment" | "orderableIndex" | "queue">} props */
function SegmentOrderControls({ segment, orderableIndex, queue }) {
  const { orderableKeys, reordering, applyOrder } = queue;
  const segmentLabel = segment.scope?.listing || segment.agent_family;
  return (
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
            moveSegmentKey(orderableKeys, segment.segment_key, orderableIndex - 1),
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
            moveSegmentKey(orderableKeys, segment.segment_key, orderableIndex + 1),
          )
        }
      >
        <ArrowDown size={15} />
      </button>
    </div>
  );
}

/** @param {Pick<SegmentDetailProps, "task" | "segment" | "canOrder" | "orderableIndex" | "queue" | "onViewLogs">} props */
function SegmentSecondaryActions({
  task,
  segment,
  canOrder,
  orderableIndex,
  queue,
  onViewLogs,
}) {
  return (
    <div className="listing-secondary-actions">
      {onViewLogs && (
        <button
          type="button"
          className="secondary-button compact-button"
          onClick={() => onViewLogs(segment)}
        >
          查看此 Listing 日志
        </button>
      )}
      {canOrder && (
        <SegmentOrderControls
          segment={segment}
          orderableIndex={orderableIndex}
          queue={queue}
        />
      )}
      {["completed", "completed_with_errors"].includes(segment.status) &&
        isPublishedResult(segment) && (
          <ResultDownloadButton
            key={segment.result_version_id}
            versionId={segment.result_version_id}
            compact
          />
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
  );
}

/** @param {SegmentDetailProps} props */
export function SegmentBoardDetail({
  task,
  segment,
  canOrder,
  orderableIndex,
  queue,
  stateDescription,
  stateLabel,
  onViewLogs,
}) {
  return (
    <div className="listing-row-detail" role="cell">
      <SegmentModelMetrics segment={segment} />
      <SegmentDetailFacts
        task={task}
        segment={segment}
        stateLabel={stateLabel}
        stateDescription={stateDescription}
      />
      <SegmentRunConfiguration segment={segment} />
      <SegmentSecondaryActions
        task={task}
        segment={segment}
        canOrder={canOrder}
        orderableIndex={orderableIndex}
        queue={queue}
        onViewLogs={onViewLogs}
      />
    </div>
  );
}
