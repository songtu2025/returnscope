import { useCallback, useRef } from "react";
import useSWR from "swr";

import { api } from "../../api";
import { errorMessage } from "../../shared/api/requestErrors";
import { serverStateKeys } from "../../shared/serverState";
import { runResultRequest } from "./resultRequestLifecycle";

/** @param {string} version */
export function useClassificationResultOverview(version) {
  const controllerRef = useRef(/** @type {AbortController | null} */ (null));
  const loadOverview = useCallback(
    () =>
      runResultRequest(
        controllerRef,
        (signal) =>
          Promise.all([
            api.classificationResult(version, { signal }),
            api.classificationResultSummary(version, { signal }),
          ]),
        ([result, summary]) => ({ result, summary }),
      ),
    [version],
  );
  const {
    data: overview,
    error,
    isLoading,
    mutate,
  } = useSWR(serverStateKeys.classificationResultOverview(version), loadOverview);
  const retry = useCallback(() => void mutate(), [mutate]);
  return {
    result: overview?.result ?? null,
    summary: overview?.summary ?? null,
    loading: isLoading,
    error: error ? errorMessage(error) : "",
    retry,
  };
}
