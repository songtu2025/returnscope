import { useDataRefresh } from "../../hooks/useDataRefresh";
import { MANAGED_REFRESH_OPTIONS } from "../../shared/refreshPolicy";
import { useCallback, useEffect, useRef } from "react";
import useSWR from "swr";

import { api } from "../../api";
import { errorMessage, errorStatus } from "../../shared/api/requestErrors";
import { serverStateKeys } from "../../shared/serverState";
import { runResultRequest } from "../../shared/api/requestLifecycle";
import { useProtectedData } from "../../hooks/useProtectedData";

/** @param {NonNullable<import("../../shared/api/generated/classification-results/types.gen").ListResultsApiClassificationResultsGetData["query"]>} query */
export function useClassificationResultListData(query, protectedOperation = false) {
  const listControllerRef = useRef(/** @type {AbortController | null} */ (null));
  const fetchResults = useCallback(
    /** @returns {Promise<import("../../shared/api/generated/classification-results/types.gen").ClassificationResultListResponse | undefined>} */
    () =>
      runResultRequest(
        listControllerRef,
        (signal) => api.classificationResults(query, { signal }),
        (value) => value,
      ),
    [query],
  );
  const {
    data: fetchedData = null,
    error: loadError,
    isLoading,
    isValidating,
    mutate,
  } = useSWR(
    serverStateKeys.classificationResultList(query),
    fetchResults,
    MANAGED_REFRESH_OPTIONS,
  );
  const data = useProtectedData(fetchedData, protectedOperation, JSON.stringify(query));
  useDataRefresh(() => mutate(), {
    loading: isLoading || isValidating,
    identity: JSON.stringify(query),
  });
  const requestIdentity = JSON.stringify(query);
  useEffect(() => () => listControllerRef.current?.abort(), [requestIdentity]);
  const load = useCallback(async () => {
    await mutate();
  }, [mutate]);
  return {
    data: [401, 403].includes(Number(errorStatus(loadError))) ? null : data,
    loading: isLoading || isValidating,
    error: loadError ? errorMessage(loadError) : "",
    load,
  };
}
