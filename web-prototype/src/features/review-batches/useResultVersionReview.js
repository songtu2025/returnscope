import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { errorMessage, errorStatus } from "../../shared/api/requestErrors";
import { activeReviewBatch } from "../classification-results/resultActionPolicy";
/** @typedef {import("../../shared/api/reviewBatchContracts").ResultVersion} ResultVersion */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewBatch} ReviewBatch */

/**
 * @param {string} resultVersionId
 * @param {(message: string, type?: string) => void} notify
 * @param {(batch: ReviewBatch) => void} openBatch
 */
export function useResultVersionReview(resultVersionId, notify, openBatch) {
  const [state, setState] = useState(
    /** @type {{loading: boolean, error: string, history: ResultVersion[], batches: ReviewBatch[]}} */ ({
      loading: true,
      error: "",
      history: [],
      batches: [],
    }),
  );
  const [createOpen, setCreateOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [creating, setCreating] = useState(false);
  const generationRef = useRef(0);
  const controllerRef = useRef(/** @type {AbortController | null} */ (null));

  const load = useCallback(async () => {
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const [history, batches] = await Promise.all([
        api.classificationResultVersions(resultVersionId, {
          signal: controller.signal,
        }),
        api.reviewBatches(
          {
            page: 1,
            page_size: 100,
            base_result_version_id: resultVersionId,
          },
          { signal: controller.signal },
        ),
      ]);
      if (generationRef.current === generation) {
        setState({
          loading: false,
          error: "",
          history,
          batches: batches.items ?? [],
        });
      }
    } catch (error) {
      if (
        generationRef.current === generation &&
        !(error instanceof Error && error.name === "AbortError")
      ) {
        setState((current) => ({
          ...current,
          loading: false,
          error: errorMessage(error),
        }));
      }
    }
  }, [resultVersionId]);

  useEffect(() => {
    load();
    return () => {
      generationRef.current += 1;
      controllerRef.current?.abort();
    };
  }, [load]);

  const createBatch = async () => {
    if (!reason.trim()) return;
    setCreating(true);
    try {
      const batch = await api.createReviewBatch(resultVersionId, {
        reason: reason.trim(),
      });
      notify("复核批次已创建");
      setCreateOpen(false);
      openBatch(batch);
    } catch (error) {
      if (error instanceof Error && errorStatus(error) === 409) {
        try {
          const batches = await api.reviewBatches({
            page: 1,
            page_size: 100,
            base_result_version_id: resultVersionId,
          });
          const draft = activeReviewBatch(batches.items ?? []);
          if (draft) {
            notify("该版本已有复核批次，已为你打开");
            setCreateOpen(false);
            openBatch(draft);
            return;
          }
        } catch (refreshError) {
          notify(errorMessage(refreshError), "error");
          return;
        }
      }
      notify(errorMessage(error), "error");
    } finally {
      setCreating(false);
    }
  };

  return {
    state,
    load,
    createOpen,
    setCreateOpen,
    reason,
    setReason,
    creating,
    createBatch,
  };
}
