import { useClassificationResultOverview } from "./useClassificationResultOverview";
import { useClassificationResultRecords } from "./useClassificationResultRecords";

/** @typedef {import("./classificationResultRoute").ClassificationResultRoute} ClassificationResultRoute */
/** @param {{ route: ClassificationResultRoute, notify: (message: string, type: "error") => void }} options */
export function useClassificationResultDetailData({ route, notify }) {
  const overview = useClassificationResultOverview(route.version);
  const records = useClassificationResultRecords({ route, notify });
  return {
    result: overview.result,
    summary: overview.summary,
    records: records.records,
    drilldowns: records.drilldowns,
    loading: overview.loading,
    recordsLoading: records.recordsLoading,
    recordsError: records.recordsError,
    retryRecords: records.retryRecords,
    error: overview.error,
    retry: overview.retry,
  };
}
