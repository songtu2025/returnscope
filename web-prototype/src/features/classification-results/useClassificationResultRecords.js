import { useCallback, useEffect, useMemo, useRef } from "react";
import useSWR from "swr";

import { api } from "../../api";
import { errorMessage } from "../../shared/api/requestErrors";
import { serverStateKeys } from "../../shared/serverState";
import { runResultRequest } from "./resultRequestLifecycle";

/** @typedef {import("./classificationResultRoute").ClassificationResultRoute} ClassificationResultRoute */
/** @param {{ route: ClassificationResultRoute, notify: (message: string, type: "error") => void }} options */
export function useClassificationResultRecords({ route, notify }) {
  const recordsControllerRef = useRef(/** @type {AbortController | null} */ (null));
  const detailQuery = useMemo(
    () => ({
      page: route.recordPage,
      page_size: route.pageSize,
      problem: route.problem,
      product_name: route.productName,
      product_sku: route.productSku,
      order_id: route.orderId,
      quality_status: route.recordQualityStatus,
      comment_status: route.commentStatus,
      ...(route.systemRerunRequired
        ? { system_rerun_required: route.systemRerunRequired }
        : {}),
    }),
    [
      route.orderId,
      route.recordQualityStatus,
      route.commentStatus,
      route.systemRerunRequired,
      route.pageSize,
      route.problem,
      route.productName,
      route.productSku,
      route.recordPage,
    ],
  );

  const loadRecords = useCallback(
    () =>
      runResultRequest(
        recordsControllerRef,
        (signal) =>
          Promise.all([
            api.classificationResultRecordGroups(route.version, detailQuery, {
              signal: signal,
            }),
            api.classificationResultDrilldown(
              route.version,
              "problem",
              { page: 1, page_size: 100 },
              { signal: signal },
            ),
            api.classificationResultDrilldown(
              route.version,
              "product_name",
              { page: 1, page_size: 100, problem: route.problem },
              { signal: signal },
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
              { signal: signal },
            ),
          ]),
        ([records, problems, names, skus]) => ({
          records,
          drilldowns: {
            problem: problems.items ?? [],
            product_name: names.items ?? [],
            product_sku: skus.items ?? [],
          },
        }),
      ),
    [detailQuery, route.problem, route.productName, route.version],
  );
  const {
    data: recordData,
    error: recordsError,
    isLoading: recordsLoading,
    mutate,
  } = useSWR(
    route.tab === "history"
      ? null
      : serverStateKeys.classificationResultRecords(route.version, detailQuery),
    loadRecords,
  );

  useEffect(() => {
    if (!recordsError) return;
    notify(errorMessage(recordsError), "error");
  }, [notify, recordsError]);

  const emptyDrilldowns = { problem: [], product_name: [], product_sku: [] };
  return {
    records: recordData?.records ?? null,
    drilldowns: recordData?.drilldowns ?? emptyDrilldowns,
    recordsLoading: route.tab === "history" ? false : recordsLoading,
    recordsError: recordsError ? errorMessage(recordsError) : "",
    retryRecords: () => void mutate(),
  };
}
