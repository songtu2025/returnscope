import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { taxonomyPath } from "../../lib/taxonomyPresentation";
import { reviewBatchApi } from "../../shared/api/reviewBatchApi";

/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewBatch} ReviewBatch */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewBatchRoute} ReviewBatchRoute */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewLabel} ReviewLabel */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewRecordPage} ReviewRecordPage */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewRequestError} ReviewRequestError */

/** @param {unknown} error @returns {ReviewRequestError} */
function requestError(error) {
  return error instanceof Error
    ? /** @type {ReviewRequestError} */ (error)
    : /** @type {ReviewRequestError} */ (new Error("复核请求失败"));
}

/** @param {{route: ReviewBatchRoute, notify: (message: string, type?: "success" | "error") => void}} options */
export function useReviewBatchData({ route, notify }) {
  const [batchState, setBatchState] = useState(
    /** @type {{loading: boolean, error: ReviewRequestError | null, data: ReviewBatch | null}} */ ({
      loading: true,
      error: null,
      data: null,
    }),
  );
  const [recordsState, setRecordsState] = useState(
    /** @type {{loading: boolean, error: ReviewRequestError | null, data: ReviewRecordPage | null}} */ ({
      loading: true,
      error: null,
      data: null,
    }),
  );
  const [labels, setLabels] = useState(/** @type {ReviewLabel[]} */ ([]));
  const batchGeneration = useRef(0);
  const recordGeneration = useRef(0);
  const batchController = useRef(/** @type {AbortController | null} */ (null));
  const recordsController = useRef(/** @type {AbortController | null} */ (null));

  const recordQuery = useMemo(
    () => ({
      page: route.page,
      page_size: route.pageSize,
      workflow_status: route.status,
      q: route.q,
      listing: route.listing,
      product_name: route.productName,
      product_sku: route.productSku,
      order_id: route.orderId,
    }),
    [
      route.listing,
      route.orderId,
      route.page,
      route.pageSize,
      route.productName,
      route.productSku,
      route.q,
      route.status,
    ],
  );

  const loadBatch = useCallback(async () => {
    const generation = batchGeneration.current + 1;
    batchGeneration.current = generation;
    batchController.current?.abort();
    const controller = new AbortController();
    batchController.current = controller;
    setBatchState((current) => ({ ...current, loading: true, error: null }));
    try {
      const data = await reviewBatchApi.reviewBatch(route.batchId, {
        signal: controller.signal,
      });
      if (batchGeneration.current === generation) {
        setBatchState({ loading: false, error: null, data });
      }
      return data;
    } catch (error) {
      const failure = requestError(error);
      if (batchGeneration.current === generation && failure.name !== "AbortError") {
        setBatchState({ loading: false, error: failure, data: null });
      }
      throw failure;
    }
  }, [route.batchId]);

  const loadRecords = useCallback(async () => {
    const generation = recordGeneration.current + 1;
    recordGeneration.current = generation;
    recordsController.current?.abort();
    const controller = new AbortController();
    recordsController.current = controller;
    setRecordsState((current) => ({ ...current, loading: true, error: null }));
    try {
      const data = await reviewBatchApi.reviewBatchRecords(route.batchId, recordQuery, {
        signal: controller.signal,
      });
      if (recordGeneration.current === generation) {
        setRecordsState({ loading: false, error: null, data });
      }
      return data;
    } catch (error) {
      const failure = requestError(error);
      if (recordGeneration.current === generation && failure.name !== "AbortError") {
        setRecordsState({ loading: false, error: failure, data: null });
      }
      throw failure;
    }
  }, [recordQuery, route.batchId]);

  useEffect(() => {
    loadBatch().catch(() => {});
    return () => {
      batchGeneration.current += 1;
      batchController.current?.abort();
    };
  }, [loadBatch]);

  useEffect(() => {
    loadRecords().catch(() => {});
    return () => {
      recordGeneration.current += 1;
      recordsController.current?.abort();
    };
  }, [loadRecords]);

  useEffect(() => {
    const resultVersionId = batchState.data?.base_result_version_id;
    if (!resultVersionId) return undefined;
    const controller = new AbortController();
    reviewBatchApi
      .reviewTaxonomy(resultVersionId, { signal: controller.signal })
      .then((value) =>
        setLabels(
          (value.labels ?? []).map((label) => ({
            ...label,
            label_path: taxonomyPath(value, label),
          })),
        ),
      )
      .catch((error) => {
        const failure = requestError(error);
        if (failure.name !== "AbortError") notify(failure.message, "error");
      });
    return () => controller.abort();
  }, [batchState.data?.base_result_version_id, notify]);

  return {
    batchState,
    recordsState,
    labels,
    recordQuery,
    loadBatch,
    loadRecords,
    setBatchState,
    setRecordsState,
  };
}
