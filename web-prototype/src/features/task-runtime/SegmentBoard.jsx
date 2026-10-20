import { useEffect, useMemo, useRef, useState } from "react";
import { useSegmentBoardView } from "./useSegmentBoardView";
import { SegmentBoardPagination } from "./SegmentBoardPagination";
import { SegmentBoardToolbar } from "./SegmentBoardToolbar";
import {
  SegmentBoardHeader,
  ExcludedListingsSummary,
  SegmentSelectionHeading,
  EmptyListingsSummary,
} from "./SegmentBoardSummary";
import { SegmentBoardRow } from "./SegmentBoardRow";
import { isLegacyResult, isPublishedResult } from "./taskSegmentPolicy";
import { segmentNeedsAttention } from "./taskRegistryPolicy";
import { useSegmentSelection } from "./useSegmentSelection";
import { SegmentBatchControls } from "./SegmentBatchControls";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment */
/** @typedef {import("./taskRuntimeContracts").SegmentAction} SegmentAction */
/**
 * @typedef {Object} SegmentBoardProps
 * @property {AnalysisTask} task
 * @property {boolean} [disabled]
 * @property {boolean} [readRequired]
 * @property {string | null} [focusSegmentId]
 * @property {string} [initialFilter]
 * @property {import("./useSegmentBoardView").SegmentBoardReturnRef} [returnState]
 * @property {(segment: TaskSegment) => void} onRetry
 * @property {(segment: TaskSegment) => void} [onViewLogs]
 * @property {(segmentId: string) => Promise<unknown>} onRetryPublish
 * @property {(segmentKey: string, action: SegmentAction, note?: string) => Promise<unknown>} onAction
 * @property {import("./taskSegmentBatchActions").ApplySegmentBatch} [onBatchAction]
 * @property {() => Promise<boolean>} [onRefresh]
 * @property {(maxParallelSegments: number) => Promise<unknown>} onParallelism
 * @property {(segmentKeys: string[]) => Promise<unknown>} onReorder
 * @property {(segment: TaskSegment & {result_version_id: string}, qualityStatus?: string, systemRerunRequired?: string) => void} onViewClassification
 */
const ORDERABLE_SEGMENT_STATUSES = ["queued", "retry_pending", "paused"];
const PAGE_SIZE = 20;

/** @param {TaskSegment} segment @param {string} filter */
function matchesStatusFilter(segment, filter) {
  if (filter === "all") return true;
  if (filter === "active") {
    return [
      "queued",
      "retry_pending",
      "running",
      "pause_pending",
      "cancel_pending",
      "paused",
    ].includes(segment.display_status || segment.status);
  }
  if (filter === "attention") {
    return segmentNeedsAttention(segment);
  }
  if (filter === "delivered") {
    return isPublishedResult(segment) || isLegacyResult(segment);
  }
  return segment.status === filter;
}

/** @param {SegmentBoardProps} props */
export function SegmentBoard({
  task,
  disabled = false,
  readRequired = false,
  focusSegmentId,
  initialFilter = "all",
  returnState,
  onRetry,
  onRetryPublish,
  onAction,
  onBatchAction,
  onRefresh,
  onParallelism,
  onReorder,
  onViewClassification,
  onViewLogs,
}) {
  const [reordering, setReordering] = useState(false);
  const [changingParallelism, setChangingParallelism] = useState(false);
  const [retryingPublishId, setRetryingPublishId] = useState(
    /** @type {string | null} */ (null),
  );
  const queueSegments = useMemo(
    () =>
      (task.segments ?? []).filter(
        (segment) => segment.agent_key !== "unknown" && !segment.deleted_at,
      ),
    [task.segments],
  );
  const {
    query,
    setQuery,
    deferredQuery,
    statusFilter,
    setStatusFilter,
    page,
    setPage,
    expandedSegmentKey,
    setExpandedSegmentKey,
    remember,
  } = useSegmentBoardView({
    taskId: task.id,
    segments: queueSegments,
    pageSize: PAGE_SIZE,
    focusSegmentId,
    initialFilter,
    returnState,
  });
  const focusedSegmentRef = useRef(/** @type {HTMLElement | null} */ (null));
  useEffect(() => {
    if (!focusSegmentId || !focusedSegmentRef.current) return;
    focusedSegmentRef.current.scrollIntoView({ block: "center" });
  }, [focusSegmentId, page]);
  const excludedSegments = useMemo(
    () =>
      (task.segments ?? []).filter(
        (segment) => segment.agent_key === "unknown" && !segment.deleted_at,
      ),
    [task.segments],
  );
  const selection = useSegmentSelection(
    queueSegments,
    JSON.stringify([task.id, query, statusFilter]),
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
  const canManageQueue =
    !disabled && !readRequired && ["queued", "running", "paused"].includes(task.status);
  const orderableKeys = queueSegments
    .filter((segment) => ORDERABLE_SEGMENT_STATUSES.includes(segment.status))
    .map((segment) => segment.segment_key);
  const filteredQueueSegments = useMemo(
    () =>
      queueSegments.filter((segment) => {
        const searchText = [
          segment.scope?.listing,
          segment.scope?.store,
          segment.standard_name,
          segment.agent_family,
          segment.variants?.map((variant) => variant.category_b).join(" "),
        ]
          .filter(Boolean)
          .join(" ")
          .toLocaleLowerCase();
        return (
          (!deferredQuery || searchText.includes(deferredQuery)) &&
          (statusFilter === "deleted" || matchesStatusFilter(segment, statusFilter))
        );
      }),
    [deferredQuery, queueSegments, statusFilter],
  );
  const totalPages = Math.max(Math.ceil(filteredQueueSegments.length / PAGE_SIZE), 1);
  const pageSegments = filteredQueueSegments.slice(
    (page - 1) * PAGE_SIZE,
    page * PAGE_SIZE,
  );
  const currentPageKeys = pageSegments.map((segment) => segment.segment_key);
  const batchEnabled = Boolean(onBatchAction && onRefresh);

  useEffect(() => {
    setPage((current) => Math.min(current, totalPages));
  }, [totalPages, setPage]);

  /** @param {string[]} segmentKeys */
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
      <SegmentBoardHeader count={queueSegments.length} />
      <SegmentBoardToolbar
        task={task}
        query={query}
        statusFilter={statusFilter}
        setQuery={setQuery}
        setStatusFilter={setStatusFilter}
        disabled={disabled || selection.busy}
        parallelism={{
          changingParallelism,
          setChangingParallelism,
          canManageQueue,
          maxParallelSegments,
          ownerRunningSegments,
          onParallelism,
        }}
      />
      {onBatchAction && onRefresh && (
        <SegmentBatchControls
          selection={selection}
          disabled={disabled}
          onApply={onBatchAction}
          onRefresh={onRefresh}
          readRequired={readRequired}
        />
      )}
      {queueSegments.length === 0 && (
        <EmptyListingsSummary task={task} excludedCount={excludedSegments.length} />
      )}
      {queueSegments.length > 0 && (
        <>
          <div className="listing-table" role="table">
            <div className="listing-table-head" role="row">
              <SegmentSelectionHeading
                keys={currentPageKeys}
                selection={batchEnabled ? selection : undefined}
                disabled={disabled || selection.busy}
              />
              <span>分类标准</span>
              <span>执行状态</span>
              <span>结果</span>
              <span>评论进度</span>
              <span>操作</span>
            </div>
            {pageSegments.map((segment, segmentIndex) => (
              <SegmentBoardRow
                key={segment.segment_key}
                task={task}
                segment={segment}
                position={{
                  segmentIndex,
                  page,
                  pageSize: PAGE_SIZE,
                  focusSegmentId,
                  focusedSegmentRef,
                  selection: batchEnabled
                    ? {
                        selected: selection.keys.has(segment.segment_key),
                        disabled: disabled || selection.busy,
                        onToggle: () => selection.toggle([segment.segment_key]),
                      }
                    : undefined,
                }}
                queue={{ canManageQueue, orderableKeys, reordering, applyOrder }}
                rowState={{
                  disabled: disabled || readRequired || selection.busy,
                  expandedSegmentKey,
                  setExpandedSegmentKey,
                  retryingPublishId,
                  setRetryingPublishId,
                }}
                actions={{
                  onViewLogs,
                  onAction,
                  onRetry,
                  onViewClassification: (
                    segment,
                    qualityStatus,
                    systemRerunRequired,
                  ) => {
                    remember(segment);
                    onViewClassification(segment, qualityStatus, systemRerunRequired);
                  },
                  onRetryPublish,
                }}
              />
            ))}
            {pageSegments.length === 0 && (
              <div className="listing-table-empty">没有匹配的 Listing。</div>
            )}
          </div>
          <SegmentBoardPagination
            total={filteredQueueSegments.length}
            pageSize={PAGE_SIZE}
            page={page}
            totalPages={totalPages}
            setPage={setPage}
          />
        </>
      )}
      <ExcludedListingsSummary
        count={excludedSegments.length}
        excludedRecords={excludedRecords}
        excludedComments={excludedComments}
      />
    </section>
  );
}
