import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { navigateHash } from "../../app/hashRouter";
import { reviewBatchApi } from "../../shared/api/reviewBatchApi";
import { ReviewBatchListView } from "./ReviewBatchListView";

/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewBatchRoute} ReviewBatchRoute */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewRequestError} ReviewRequestError */

/** @param {unknown} error @returns {ReviewRequestError} */
function requestError(error) {
  return error instanceof Error
    ? /** @type {ReviewRequestError} */ (error)
    : /** @type {ReviewRequestError} */ (new Error("复核批次读取失败"));
}

/** @param {{route: ReviewBatchRoute, updateRoute: (changes: Partial<ReviewBatchRoute>) => void}} props */
export function ReviewBatchList({ route, updateRoute }) {
  const [state, setState] = useState(
    /** @type {import("./ReviewBatchListView").ReviewBatchListViewProps["state"]} */ ({
      loading: true,
      error: null,
      data: null,
    }),
  );
  const [filters, setFilters] = useState({ q: route.q, status: route.status });
  const generationRef = useRef(0);
  const controllerRef = useRef(/** @type {AbortController | null} */ (null));

  useEffect(() => {
    setFilters({ q: route.q, status: route.status });
  }, [route.q, route.status]);

  const query = useMemo(
    () => ({
      page: route.page,
      page_size: route.pageSize,
      status: route.status,
      base_result_version_id: route.resultVersionId,
      q: route.q,
    }),
    [route.page, route.pageSize, route.q, route.resultVersionId, route.status],
  );

  const load = useCallback(async () => {
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const data = await reviewBatchApi.reviewBatches(query, {
        signal: controller.signal,
      });
      if (generationRef.current === generation) {
        setState({ loading: false, error: null, data });
      }
    } catch (error) {
      const failure = requestError(error);
      if (generationRef.current === generation && failure.name !== "AbortError") {
        setState({ loading: false, error: failure, data: null });
      }
    }
  }, [query]);

  useEffect(() => {
    load();
    return () => {
      generationRef.current += 1;
      controllerRef.current?.abort();
    };
  }, [load]);

  const openNeedsReviewResults = () =>
    navigateHash("classification-results", { quality_status: "review_required" });

  return (
    <ReviewBatchListView
      state={state}
      route={route}
      filters={filters}
      onFilters={setFilters}
      updateRoute={updateRoute}
      onRetry={load}
      onEmptyAction={openNeedsReviewResults}
    />
  );
}
