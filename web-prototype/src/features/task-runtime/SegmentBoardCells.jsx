import { isLegacyResult } from "./taskSegmentPolicy";
import { SEGMENT_STATUS_LABELS } from "./segmentBoardRowPolicy";
import { segmentNeedsAttention } from "./taskRegistryPolicy";

/** @typedef {import("./segmentBoardRowContracts").SegmentBoardRowProps} SegmentBoardRowProps */
/** @typedef {Pick<SegmentBoardRowProps, "task" | "segment" | "position"> & {presentation: ReturnType<typeof import("./segmentBoardRowPolicy").segmentResultPresentation>, primaryActions: import("react").ReactNode}} SegmentCellsProps */

/** @param {Pick<SegmentCellsProps, "segment" | "presentation">} props */
function SegmentResultCells({ segment, presentation }) {
  const { displayStatus, publishStatus, qualityState, stateLabel, stateDescription } =
    presentation;
  return (
    <>
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
              ? "旧结果"
              : stateLabel
            : "未生成"}
        </span>
        {publishStatus === "failed" && (
          <small className="result-publish-error">{stateDescription}</small>
        )}
      </div>
    </>
  );
}

/** @param {Pick<SegmentCellsProps, "segment">} props */
function SegmentProgressCell({ segment }) {
  const progress = segment.progress_total
    ? Math.round((segment.progress_current / segment.progress_total) * 100)
    : 0;
  return (
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
  );
}

/** @param {SegmentCellsProps} props */
export function SegmentBoardCells({
  task,
  segment,
  position,
  presentation,
  primaryActions,
}) {
  const { segmentIndex, page, pageSize } = position;
  return (
    <>
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
      <SegmentResultCells segment={segment} presentation={presentation} />
      <SegmentProgressCell segment={segment} />
      {primaryActions}
      {segment.error && segmentNeedsAttention(segment) && (
        <p className="segment-error">{segment.error}</p>
      )}
    </>
  );
}
