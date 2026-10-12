import { useCallback, useEffect, useEffectEvent, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api } from "../../api";
import { useDataRefresh } from "../../hooks/useDataRefresh";
import { useProtectedData } from "../../hooks/useProtectedData";
import { MANAGED_REFRESH_OPTIONS } from "../../shared/refreshPolicy";
import { runResultRequest } from "../../shared/api/requestLifecycle";
import { errorMessage } from "../../shared/api/requestErrors";
import { serverStateKeys } from "../../shared/serverState";
import {
  readResultOverview,
  readResultRecords,
  resultRecordQuery,
} from "./classificationResultReads";

/** @param {{route: import("./classificationResultRoute").ClassificationResultRoute, result: ReturnType<typeof import("./useClassificationResultOverview").useClassificationResultOverview>["result"], protectedOperation: boolean, updateRoute: (changes: Partial<import("./classificationResultRoute").ClassificationResultRoute>) => void, refreshAttempt: number}} options */
export function useLatestResult({
  route,
  result,
  protectedOperation,
  updateRoute,
  refreshAttempt,
}) {
  const { mutate: mutateCache } = useSWRConfig();
  const [syncError, setSyncError] = useState("");
  const controllerRef = useRef(/** @type {AbortController | null} */ (null));
  const load = useCallback(
    () =>
      runResultRequest(
        controllerRef,
        (signal) => api.classificationResultVersions(route.version, { signal }),
        (value) => value,
      ),
    [route.version],
  );
  const enabled = Boolean(result) && route.tab !== "history";
  const { data, error, mutate, isValidating } = useSWR(
    enabled ? ["classification-results", "versions", route.version] : null,
    load,
    MANAGED_REFRESH_OPTIONS,
  );
  const displayed = useProtectedData(data, protectedOperation, route.version);
  useDataRefresh(() => mutate(), {
    enabled,
    loading: isValidating,
    identity: route.version,
  });
  const prepareLatest = useEffectEvent(
    async (/** @type {string} */ version, /** @type {AbortSignal} */ signal) => {
      const query = resultRecordQuery(route);
      const [overview, records] = await Promise.all([
        readResultOverview(version, { signal }),
        readResultRecords(version, query, { signal }),
      ]);
      if (signal.aborted) return;
      await Promise.all([
        mutateCache(serverStateKeys.classificationResultOverview(version), overview, {
          revalidate: false,
        }),
        mutateCache(
          serverStateKeys.classificationResultRecords(version, query),
          records,
          { revalidate: false },
        ),
      ]);
      if (!signal.aborted) {
        setSyncError("");
        updateRoute({ version });
      }
    },
  );
  const queryIdentity = JSON.stringify(resultRecordQuery(route));
  useEffect(() => {
    if (!displayed || !result || protectedOperation) return;
    const latest = displayed.find((version) => version.publish_status === "published");
    if (!(
      latest &&
      latest.version > result.version &&
      latest.version_id !== route.version
    ))
      return;
    const controller = new AbortController();
    // 先备齐同一版本的摘要和反馈，再整体切换，后台更新不清空页面或重置分页。
    prepareLatest(latest.version_id, controller.signal).catch((failure) => {
      if (!controller.signal.aborted) setSyncError(errorMessage(failure));
    });
    return () => controller.abort();
  }, [displayed, protectedOperation, result, route.version, queryIdentity]);
  useEffect(() => {
    if (refreshAttempt) void mutate();
  }, [mutate, refreshAttempt]);
  useEffect(() => () => controllerRef.current?.abort(), [route.version]);
  return syncError || (error ? errorMessage(error) : "");
}
