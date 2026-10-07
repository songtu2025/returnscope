import { useCallback, useEffect, useState } from "react";
import { auditApi } from "../../shared/api/auditApi";
import { filtersFromRoute, getDateRangeError, PAGE_SIZE } from "./auditLogPolicy";

/** @typedef {import("../../shared/api/systemSettingsContracts").AuditLogPage} AuditPageData */
/** @param {import("./auditLogPolicy").AuditRoute} route @param {number} page */
export function useAuditLogs(route, page) {
  const [state, setState] = useState(
    /** @type {{loading: boolean, error: string, data: AuditPageData | null}} */ ({
      loading: true,
      error: "",
      data: null,
    }),
  );
  const load = useCallback(
    /** @param {AbortSignal} [signal] */
    async (signal) => {
      if (
        getDateRangeError({
          date_from: route.query.date_from || "",
          date_to: route.query.date_to || "",
        })
      ) {
        setState({ loading: false, error: "", data: null });
        return;
      }
      setState({ loading: true, error: "", data: null });
      try {
        const data = await auditApi.logs(
          {
            ...filtersFromRoute({ query: route.query }),
            page,
            page_size: PAGE_SIZE,
          },
          { signal },
        );
        setState({ loading: false, error: "", data });
      } catch (error) {
        const requestError =
          error instanceof Error ? error : new Error("审计记录读取失败");
        if (requestError.name !== "AbortError") {
          setState({ loading: false, error: requestError.message, data: null });
        }
      }
    },
    [page, route.query],
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  return { state, load };
}
