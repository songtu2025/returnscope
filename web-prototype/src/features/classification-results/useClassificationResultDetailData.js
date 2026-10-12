import { useMemo } from "react";
import { useProtectedData } from "../../hooks/useProtectedData";
import { useClassificationResultOverview } from "./useClassificationResultOverview";
import { useClassificationResultRecords } from "./useClassificationResultRecords";

/** @typedef {import("./classificationResultRoute").ClassificationResultRoute} ClassificationResultRoute */
/** @param {{ route: ClassificationResultRoute, notify: (message: string, type: "error") => void, protectedOperation?: boolean }} options */
export function useClassificationResultDetailData({
  route,
  notify,
  protectedOperation = false,
}) {
  const overview = useClassificationResultOverview(route.version);
  const records = useClassificationResultRecords({ route, notify });
  const snapshot = useMemo(
    () => ({
      result: overview.result,
      summary: overview.summary,
      records: records.records,
      drilldowns: records.drilldowns,
    }),
    [overview.result, overview.summary, records.records, records.drilldowns],
  );
  const current = useProtectedData(snapshot, protectedOperation, JSON.stringify(route));
  return {
    result: current.result,
    summary: current.summary,
    records: current.records,
    drilldowns: current.drilldowns,
    loading: overview.loading,
    recordsLoading: records.recordsLoading,
    recordsError: records.recordsError,
    retryRecords: records.retryRecords,
    error: overview.error,
    retry: overview.retry,
  };
}
