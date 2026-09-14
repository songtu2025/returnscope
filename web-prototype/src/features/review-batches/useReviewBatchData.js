import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { taxonomyPath } from "../../lib/taxonomyPresentation";
import { reviewBatchApi } from "../../shared/api/reviewBatchApi";

export function useReviewBatchData({ route, notify }) {
  const [batchState, setBatchState] = useState({
    loading: true,
    error: null,
    data: null,
  });
  const [recordsState, setRecordsState] = useState({
    loading: true,
    error: null,
    data: null,
  });
  const [labels, setLabels] = useState([]);
  const batchGeneration = useRef(0);
  const recordGeneration = useRef(0);
  const batchController = useRef(null);
  const recordsController = useRef(null);

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
      if (batchGeneration.current === generation && error.name !== "AbortError") {
        setBatchState({ loading: false, error, data: null });
      }
      throw error;
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
      if (recordGeneration.current === generation && error.name !== "AbortError") {
        setRecordsState({ loading: false, error, data: null });
      }
      throw error;
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
        if (error.name !== "AbortError") notify(error.message, "error");
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
