import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { AntdProvider } from "../../components/AntdProvider";
import { ResultVersionHistory } from "./ResultVersionHistory";
import { errorMessage } from "../analysis-dashboards/dashboardRequestErrors";

/** @typedef {import("../../shared/api/reviewBatchContracts").ResultVersion} ResultVersion */
/** @param {{result: {version_id: string}, onSelectVersion: (versionId: string) => void}} props */
export function ResultVersionReviewPanel({ result, onSelectVersion }) {
  const controllerRef = useRef(/** @type {AbortController | null} */ (null));
  const [state, setState] = useState({
    id: result.version_id,
    history: /** @type {ResultVersion[]} */ ([]),
    loading: true,
    error: "",
  });
  const load = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState((current) => ({
      id: result.version_id,
      history: current.id === result.version_id ? current.history : [],
      loading: true,
      error: "",
    }));
    try {
      const history = await api.classificationResultVersions(result.version_id, {
        signal: controller.signal,
      });
      if (!controller.signal.aborted)
        setState({ id: result.version_id, history, loading: false, error: "" });
    } catch (reason) {
      if (!controller.signal.aborted)
        setState((current) => ({
          ...current,
          loading: false,
          error: errorMessage(reason),
        }));
    }
  }, [result.version_id]);
  useEffect(() => {
    load();
    return () => controllerRef.current?.abort();
  }, [load]);
  const current = state.id === result.version_id;
  return (
    <AntdProvider>
      <ResultVersionHistory
        history={current ? state.history : []}
        resultVersionId={result.version_id}
        loading={!current || state.loading}
        error={current ? state.error : ""}
        onReload={load}
        onSelectVersion={onSelectVersion}
      />
    </AntdProvider>
  );
}
