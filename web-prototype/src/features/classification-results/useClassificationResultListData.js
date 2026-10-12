import { useCallback, useRef } from "react";
import useSWR from "swr";

import { api } from "../../api";
import { errorMessage, errorStatus } from "../../shared/api/requestErrors";
import { serverStateKeys } from "../../shared/serverState";
import { runResultRequest } from "../../shared/api/requestLifecycle";
import { useNewResultNotice } from "./useNewResultNotice";

/** @param {NonNullable<import("../../shared/api/generated/classification-results/types.gen").ListResultsApiClassificationResultsGetData["query"]>} query */
export function useClassificationResultListData(query) {
  const listControllerRef = useRef(/** @type {AbortController | null} */ (null));
  const fetchResults = useCallback(
    () =>
      runResultRequest(
        listControllerRef,
        (signal) => api.classificationResults(query, { signal }),
        (value) => value,
      ),
    [query],
  );
  const {
    data = null,
    error: loadError,
    isLoading,
    isValidating,
    mutate,
  } = useSWR(serverStateKeys.classificationResultList(query), fetchResults);
  const { hasNewResults, resetNotice } = useNewResultNotice(query, data);
  const load = useCallback(async () => {
    resetNotice();
    await mutate();
  }, [mutate, resetNotice]);
  return {
    data: [401, 403].includes(Number(errorStatus(loadError))) ? null : data,
    loading: isLoading || isValidating,
    error: loadError ? errorMessage(loadError) : "",
    hasNewResults,
    load,
  };
}
