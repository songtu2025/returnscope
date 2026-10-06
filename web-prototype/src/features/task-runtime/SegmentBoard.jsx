import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { SegmentBoardPagination } from "./SegmentBoardPagination";
import { SegmentBoardToolbar } from "./SegmentBoardToolbar";
import { SegmentBoardHeader, ExcludedListingsSummary } from "./SegmentBoardSummary";
import { SegmentBoardRow } from "./SegmentBoardRow";
import { isLegacyResult, isPublishedResult } from "./taskSegmentPolicy";
import { segmentNeedsAttention } from "./taskRegistryPolicy";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment */
/** @typedef {import("./taskRuntimeContracts").SegmentAction} SegmentAction */
/**
 * @typedef {Object} SegmentBoardProps
 * @property {AnalysisTask} task
 * @property {string | null} [focusSegmentId]
 * @property {string} [initialFilter]
 * @property {(segment: TaskSegment) => void} onRetry
 * @property {(segmentId: string) => Promise<unknown>} onRetryPublish
 * @property {(segment: TaskSegment) => void} onCancel
 * @property {(segmentKey: string, action: SegmentAction, note?: string) => Promise<unknown>} onAction
 * @property {(maxParallelSegments: number) => Promise<unknown>} onParallelism
 * @property {(segmentKeys: string[]) => Promise<unknown>} onReorder
 * @property {(segment: TaskSegment & {result_version_id: string}) => void} onViewClassification
 * @property {() => void} onResumeUnfinished
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
  focusSegmentId,
  initialFilter = "all",
  onRetry,
  onRetryPublish,
  onCancel,
  onAction,
  onParallelism,
  onReorder,
  onViewClassification,
  onResumeUnfinished,
}) {
  const [reordering, setReordering] = useState(false);
  const [changingParallelism, setChangingParallelism] = useState(false);
  const [retryingPublishId, setRetryingPublishId] = useState(
    /** @type {string | null} */ (null),
  );
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState(initialFilter);
  const [page, setPage] = useState(1);
  const [expandedSegmentKey, setExpandedSegmentKey] = useState(
    /** @type {string | null} */ (null),
  );
  const deferredQuery = useDeferredValue(query.trim().toLocaleLowerCase());
  const focusedSegmentRef = useRef(/** @type {HTMLElement | null} */ (null));
  const handledFocus = useRef(/** @type {string | null} */ (null));

  useEffect(() => {
    if (!focusSegmentId || !focusedSegmentRef.current) return;
    focusedSegmentRef.current.scrollIntoView({ block: "center" });
  }, [focusSegmentId, page]);

  const queueSegments = useMemo(
    () => (task.segments ?? []).filter((segment) => segment.agent_key !== "unknown"),
    [task.segments],
  );
  const excludedSegments = useMemo(
    () => (task.segments ?? []).filter((segment) => segment.agent_key === "unknown"),
    [task.segments],
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
          matchesStatusFilter(segment, statusFilter)
        );
      }),
    [deferredQuery, queueSegments, statusFilter],
  );
  const totalPages = Math.max(Math.ceil(filteredQueueSegments.length / PAGE_SIZE), 1);
  const pageSegments = filteredQueueSegments.slice(
    (page - 1) * PAGE_SIZE,
    page * PAGE_SIZE,
  );

  useEffect(() => {
    setPage(1);
  }, [deferredQuery, statusFilter]);

  useEffect(() => {
    setPage((current) => Math.min(current, totalPages));
  }, [totalPages]);

  useEffect(() => {
    if (!focusSegmentId || handledFocus.current === focusSegmentId) return;
    const index = queueSegments.findIndex((segment) =>
      [segment.id, segment.segment_key].some(
        (value) => String(value) === String(focusSegmentId),
      ),
    );
    if (index >= 0) {
      handledFocus.current = focusSegmentId;
      setQuery("");
      setStatusFilter("all");
      setPage(Math.floor(index / PAGE_SIZE) + 1);
    }
  }, [focusSegmentId, queueSegments]);

  if (!task.segments?.length) return null;

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
        parallelism={{
          changingParallelism,
          setChangingParallelism,
          canManageQueue,
          maxParallelSegments,
          ownerRunningSegments,
          onParallelism,
        }}
      />
      {queueSegments.length > 0 && (
        <>
          <div className="listing-table" role="table">
            <div className="listing-table-head" role="row">
              <span>Listing</span>
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
                }}
                queue={{ canManageQueue, orderableKeys, reordering, applyOrder }}
                rowState={{
                  expandedSegmentKey,
                  setExpandedSegmentKey,
                  retryingPublishId,
                  setRetryingPublishId,
                }}
                actions={{
                  onResumeUnfinished,
                  onAction,
                  onRetry,
                  onViewClassification,
                  onRetryPublish,
                  onCancel,
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
