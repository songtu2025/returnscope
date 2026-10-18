import { useDeferredValue, useEffect, useRef, useState } from "react";

/** @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment */
/** @typedef {{taskId: string, segmentId: string, query: string, statusFilter: string, page: number, expandedSegmentKey: string | null}} SegmentBoardReturnState */
/** @typedef {import("react").MutableRefObject<SegmentBoardReturnState | null>} SegmentBoardReturnRef */

/** @param {{taskId: string, segments: TaskSegment[], pageSize: number, focusSegmentId?: string | null, initialFilter: string, returnState?: SegmentBoardReturnRef}} options */
export function useSegmentBoardView({
  taskId,
  segments,
  pageSize,
  focusSegmentId,
  initialFilter,
  returnState: snapshotRef,
}) {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState(initialFilter);
  const [page, setPage] = useState(1);
  const [expandedSegmentKey, setExpandedSegmentKey] = useState(
    /** @type {string | null} */ (null),
  );
  const deferredQuery = useDeferredValue(query.trim().toLocaleLowerCase());
  const restoredTask = useRef("");
  const handledFocus = useRef(/** @type {string | null | undefined} */ (null));

  useEffect(() => {
    if (restoredTask.current === taskId) return;
    restoredTask.current = taskId;
    const saved = snapshotRef?.current;
    if (
      !saved ||
      saved.taskId !== taskId ||
      initialFilter !== "all" ||
      (focusSegmentId && saved.segmentId !== focusSegmentId)
    )
      return;
    snapshotRef.current = null;
    handledFocus.current = focusSegmentId;
    setQuery(saved.query);
    setStatusFilter(saved.statusFilter);
    setPage(saved.page);
    setExpandedSegmentKey(saved.expandedSegmentKey);
  }, [taskId, initialFilter, focusSegmentId, snapshotRef]);

  useEffect(() => {
    if (!focusSegmentId || handledFocus.current === focusSegmentId) return;
    const index = segments.findIndex((segment) =>
      [segment.id, segment.segment_key].some(
        (value) => String(value) === String(focusSegmentId),
      ),
    );
    if (index >= 0) {
      handledFocus.current = focusSegmentId;
      setQuery("");
      setStatusFilter("all");
      setPage(Math.floor(index / pageSize) + 1);
    }
  }, [focusSegmentId, segments, pageSize]);

  /** @param {TaskSegment} segment */
  const remember = (segment) => {
    if (!snapshotRef) return;
    snapshotRef.current = {
      taskId,
      segmentId: segment.id || segment.segment_key,
      query,
      statusFilter,
      page,
      expandedSegmentKey,
    };
  };

  return {
    query,
    setQuery: (/** @type {import("react").SetStateAction<string>} */ value) => {
      setQuery(value);
      setPage(1);
    },
    deferredQuery,
    statusFilter,
    setStatusFilter: (/** @type {import("react").SetStateAction<string>} */ value) => {
      setStatusFilter(value);
      setPage(1);
    },
    page,
    setPage,
    expandedSegmentKey,
    setExpandedSegmentKey,
    remember,
  };
}
