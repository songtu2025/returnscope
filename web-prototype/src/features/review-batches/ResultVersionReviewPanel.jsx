import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import { AntdProvider } from "../../components/AntdProvider";
import { ResultVersionHistory } from "./ResultVersionHistory";
import { errorMessage } from "../analysis-dashboards/dashboardRequestErrors";

/** @typedef {import("../../shared/api/reviewBatchContracts").ResultVersion} ResultVersion */
/** @param {{result: {version_id: string}, onSelectVersion: (versionId: string) => void}} props */
export function ResultVersionReviewPanel({ result, onSelectVersion }) {
  const [history, setHistory] = useState(/** @type {ResultVersion[]} */ ([]));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(
    async (/** @type {AbortSignal | undefined} */ signal) => {
      setLoading(true);
      setError("");
      try {
        const values = await api.classificationResultVersions(result.version_id, {
          signal,
        });
        if (!signal?.aborted) setHistory(values);
      } catch (reason) {
        if (!signal?.aborted) setError(errorMessage(reason));
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [result.version_id],
  );
  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);
  return (
    <AntdProvider>
      <ResultVersionHistory
        history={history}
        resultVersionId={result.version_id}
        loading={loading}
        error={error}
        onReload={() => load(undefined)}
        onSelectVersion={onSelectVersion}
      />
    </AntdProvider>
  );
}
