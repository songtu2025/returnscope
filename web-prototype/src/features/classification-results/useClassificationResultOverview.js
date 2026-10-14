import { useDataRefresh } from "../../hooks/useDataRefresh";
import { MANAGED_REFRESH_OPTIONS } from "../../shared/refreshPolicy";
import { useCallback, useLayoutEffect, useRef } from "react";
import useSWR from "swr";

import { readResultOverview } from "./classificationResultReads";
import { errorMessage } from "../../shared/api/requestErrors";
import { serverStateKeys } from "../../shared/serverState";
import { runResultRequest } from "../../shared/api/requestLifecycle";

/** @param {string} version @param {boolean} [keepPreviousData] */
export function useClassificationResultOverview(version, keepPreviousData = false) {
  const controllerRef = useRef(/** @type {AbortController | null} */ (null));
  const loadOverview = useCallback(
    () =>
      runResultRequest(
        controllerRef,
        (signal) => readResultOverview(version, { signal }),
        (value) => value,
      ),
    [version],
  );
  const {
    data: overview,
    error,
    isLoading,
    mutate,
  } = useSWR(serverStateKeys.classificationResultOverview(version), loadOverview, {
    ...MANAGED_REFRESH_OPTIONS,
    keepPreviousData,
  });
  useDataRefresh(() => mutate(), { loading: isLoading, identity: version });
  // 在新查询启动前清理旧读取，避免被动清理误取消新请求。
  useLayoutEffect(() => () => controllerRef.current?.abort(), [version]);
  const retry = useCallback(() => void mutate(), [mutate]);
  return {
    result: overview?.result ?? null,
    summary: overview?.summary ?? null,
    loading: isLoading,
    error: error ? errorMessage(error) : "",
    retry,
  };
}
