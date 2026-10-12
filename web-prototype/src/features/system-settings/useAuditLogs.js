import { useDataRefresh } from "../../hooks/useDataRefresh";
import { MANAGED_REFRESH_OPTIONS } from "../../shared/refreshPolicy";
import { useCallback, useRef } from "react";
import useSWR from "swr";
import { auditApi } from "../../shared/api/auditApi";
import { errorMessage } from "../../shared/api/requestErrors";
import { runResultRequest } from "../../shared/api/requestLifecycle";
import { filtersFromRoute, getDateRangeError, PAGE_SIZE } from "./auditLogPolicy";

/** @param {import("./auditLogPolicy").AuditRoute} route @param {number} page */
export function useAuditLogs(route, page) {
  const filters = filtersFromRoute(route);
  const valid = !getDateRangeError(filters);
  const controllerRef = useRef(/** @type {AbortController | null} */ (null));
  const {
    data = null,
    error,
    isLoading,
    isValidating,
    mutate,
  } = useSWR(
    valid ? ["audit-logs", filters, page] : null,
    () =>
      runResultRequest(
        controllerRef,
        (signal) =>
          auditApi.logs({ ...filters, page, page_size: PAGE_SIZE }, { signal }),
        (value) => value,
      ),
    MANAGED_REFRESH_OPTIONS,
  );
  useDataRefresh(() => mutate(), {
    enabled: valid,
    loading: isLoading || isValidating,
    identity: JSON.stringify([filters, page]),
  });
  const load = useCallback(
    () => mutate((current) => current, { revalidate: true, throwOnError: false }),
    [mutate],
  );
  return {
    state: {
      data,
      loading: isLoading || isValidating,
      error: error ? errorMessage(error) : "",
    },
    load,
  };
}
