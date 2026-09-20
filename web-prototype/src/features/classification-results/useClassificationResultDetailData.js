import { useCallback, useEffect, useMemo, useRef } from "react";
import useSWR from "swr";

import { api } from "../../api";
import { serverStateKeys } from "../../shared/serverState";

/** @typedef {import("./classificationResultRoute").ClassificationResultRoute} ClassificationResultRoute */

/**
 * @param {{ route: ClassificationResultRoute, notify: (message: string, type: "error") => void }} options
 */
export function useClassificationResultDetailData({ route, notify }) {
  const overviewControllerRef = useRef(/** @type {AbortController | null} */ (null));
  const recordsControllerRef = useRef(/** @type {AbortController | null} */ (null));
  const loadOverview = useCallback(async () => {
    overviewControllerRef.current?.abort();
    const controller = new AbortController();
    overviewControllerRef.current = controller;
    try {
      const [result, summary] = await Promise.all([
        api.classificationResult(route.version, { signal: controller.signal }),
        api.classificationResultSummary(route.version, { signal: controller.signal }),
      ]);
      return { result, summary };
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return undefined;
      throw error;
    } finally {
      if (overviewControllerRef.current === controller) {
        overviewControllerRef.current = null;
      }
    }
  }, [route.version]);
  const {
    data: overview,
    error: overviewError,
    isLoading: overviewLoading,
    mutate: mutateOverview,
  } = useSWR(serverStateKeys.classificationResultOverview(route.version), loadOverview);
  const retry = useCallback(() => void mutateOverview(), [mutateOverview]);

  const detailQuery = useMemo(
    () => ({
      page: route.recordPage,
      page_size: route.pageSize,
      problem: route.problem,
      product_name: route.productName,
      product_sku: route.productSku,
      order_id: route.orderId,
    }),
    [
      route.orderId,
      route.pageSize,
      route.problem,
      route.productName,
      route.productSku,
      route.recordPage,
    ],
  );

  const loadRecords = useCallback(async () => {
    recordsControllerRef.current?.abort();
    const controller = new AbortController();
    recordsControllerRef.current = controller;
    try {
      const [records, problems, names, skus] = await Promise.all([
        api.classificationResultRecords(route.version, detailQuery, {
          signal: controller.signal,
        }),
        api.classificationResultDrilldown(
          route.version,
          "problem",
          { page: 1, page_size: 100 },
          { signal: controller.signal },
        ),
        api.classificationResultDrilldown(
          route.version,
          "product_name",
          { page: 1, page_size: 100, problem: route.problem },
          { signal: controller.signal },
        ),
        api.classificationResultDrilldown(
          route.version,
          "product_sku",
          {
            page: 1,
            page_size: 100,
            problem: route.problem,
            product_name: route.productName,
          },
          { signal: controller.signal },
        ),
      ]);
      return {
        records,
        drilldowns: {
          problem: problems.items ?? [],
          product_name: names.items ?? [],
          product_sku: skus.items ?? [],
        },
      };
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return undefined;
      throw error;
    } finally {
      if (recordsControllerRef.current === controller) {
        recordsControllerRef.current = null;
      }
    }
  }, [detailQuery, route.problem, route.productName, route.version]);
  const {
    data: recordData,
    error: recordsError,
    isLoading: recordsLoading,
  } = useSWR(
    route.tab === "history"
      ? null
      : serverStateKeys.classificationResultRecords(route.version, detailQuery),
    loadRecords,
  );

  useEffect(() => {
    if (!recordsError) return;
    notify(recordsError instanceof Error ? recordsError.message : "请求失败", "error");
  }, [notify, recordsError]);

  const emptyDrilldowns = {
    problem: [],
    product_name: [],
    product_sku: [],
  };

  return {
    result: overview?.result ?? null,
    summary: overview?.summary ?? null,
    records: recordData?.records ?? null,
    drilldowns: recordData?.drilldowns ?? emptyDrilldowns,
    loading: overviewLoading,
    recordsLoading: route.tab === "history" ? false : recordsLoading,
    error: overviewError
      ? overviewError instanceof Error
        ? overviewError.message
        : "请求失败"
      : "",
    retry,
  };
}
