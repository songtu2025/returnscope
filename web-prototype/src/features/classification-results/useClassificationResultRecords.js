import { useDataRefresh } from "../../hooks/useDataRefresh";
import { MANAGED_REFRESH_OPTIONS } from "../../shared/refreshPolicy";
import { useCallback, useEffect, useLayoutEffect, useRef } from "react";
import useSWR from "swr";

import { readResultRecords, resultRecordQuery } from "./classificationResultReads";
import { errorMessage } from "../../shared/api/requestErrors";
import { serverStateKeys } from "../../shared/serverState";
import { runResultRequest } from "../../shared/api/requestLifecycle";

const EMPTY_DRILLDOWNS = {
  problem: [],
  product_name: [],
  product_sku: [],
  totals: { product_name: 0, product_sku: 0 },
};

/** @typedef {import("./classificationResultRoute").ClassificationResultRoute} ClassificationResultRoute */
/** @param {{ route: ClassificationResultRoute, notify: (message: string, type: "error") => void, keepPreviousData?: boolean }} options */
export function useClassificationResultRecords({
  route,
  notify,
  keepPreviousData = false,
}) {
  const recordsControllerRef = useRef(/** @type {AbortController | null} */ (null));
  const detailQuery = resultRecordQuery(route);

  const loadRecords = useCallback(
    () =>
      runResultRequest(
        recordsControllerRef,
        (signal) => readResultRecords(route.version, detailQuery, { signal }),
        (value) => value,
      ),
    [detailQuery, route.version],
  );
  const {
    data: recordData,
    error: recordsError,
    isLoading: recordsLoading,
    isValidating,
    mutate,
  } = useSWR(
    route.tab === "history"
      ? null
      : serverStateKeys.classificationResultRecords(route.version, detailQuery),
    loadRecords,
    { ...MANAGED_REFRESH_OPTIONS, keepPreviousData },
  );
  useDataRefresh(() => mutate(), {
    enabled: route.tab !== "history",
    loading: recordsLoading || isValidating,
    identity: JSON.stringify([route.version, detailQuery]),
  });
  const requestIdentity = JSON.stringify([route.version, detailQuery]);
  // 在新查询启动前清理旧读取，避免被动清理误取消新请求。
  useLayoutEffect(() => () => recordsControllerRef.current?.abort(), [requestIdentity]);

  useEffect(() => {
    if (!recordsError) return;
    notify(errorMessage(recordsError), "error");
  }, [notify, recordsError]);

  return {
    records: recordData?.records ?? null,
    drilldowns: recordData?.drilldowns ?? EMPTY_DRILLDOWNS,
    recordsLoading: route.tab === "history" ? false : recordsLoading || isValidating,
    recordsError: recordsError ? errorMessage(recordsError) : "",
    retryRecords: () => void mutate(),
  };
}
