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
  // 连续复核切换到保存后的结果时，保留详情，避免抽屉被临时空数据卸载。
  const overview = useClassificationResultOverview(route.version, protectedOperation);
  const records = useClassificationResultRecords({
    route,
    notify,
    keepPreviousData: protectedOperation,
  });
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
