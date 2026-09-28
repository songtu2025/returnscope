import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { api } from "../../api";

/** @typedef {import("../../shared/api/systemSettingsContracts").ValidationRun} ValidationRun */
/** @typedef {import("../../shared/api/systemSettingsContracts").ValidationEvent} ValidationEvent */

const ACTIVE_STATUSES = ["queued", "running"];
const FINISHED_STATUSES = ["passed", "failed"];

/**
 * @param {object} options
 * @param {string | null} options.connectionId
 * @param {(message: string, type?: "success" | "error") => void} options.notify
 * @param {() => Promise<void>} options.onCompleted
 */
export function useModelValidationRun({ connectionId, notify, onCompleted }) {
  const [selection, setSelection] = useState(
    /** @type {{connectionId: string | null, run: ValidationRun | null, events: ValidationEvent[]}} */ ({
      connectionId,
      run: null,
      events: [],
    }),
  );
  const [elapsed, setElapsed] = useState(0);
  const currentConnection = useRef(connectionId);
  const lookupGeneration = useRef(0);
  const streamGeneration = useRef(0);
  const run = selection.connectionId === connectionId ? selection.run : null;
  const events = selection.connectionId === connectionId ? selection.events : [];
  const active = Boolean(run && ACTIVE_STATUSES.includes(run.status));
  const startedAt = run?.started_at ?? run?.created_at ?? null;

  useLayoutEffect(() => {
    currentConnection.current = connectionId;
  }, [connectionId]);

  useEffect(() => {
    const generation = ++lookupGeneration.current;
    streamGeneration.current += 1;
    setSelection({ connectionId, run: null, events: [] });
    setElapsed(0);
    if (connectionId) {
      api
        .activeValidation(connectionId)
        .then((value) => {
          if (lookupGeneration.current === generation && value) {
            setSelection({ connectionId, run: value, events: [] });
          }
        })
        .catch((error) => {
          if (lookupGeneration.current === generation) {
            notify(error instanceof Error ? error.message : "请求失败", "error");
          }
        });
    }
    return () => {
      lookupGeneration.current += 1;
      streamGeneration.current += 1;
    };
  }, [connectionId, notify]);

  const showRun = useCallback(
    (/** @type {ValidationRun} */ value, /** @type {string | null} */ ownerId) => {
      if (ownerId !== currentConnection.current) return false;
      lookupGeneration.current += 1;
      streamGeneration.current += 1;
      setSelection({ connectionId: ownerId, run: value, events: [] });
      return true;
    },
    [],
  );

  const clearRun = useCallback(() => {
    lookupGeneration.current += 1;
    streamGeneration.current += 1;
    setSelection({ connectionId: currentConnection.current, run: null, events: [] });
    setElapsed(0);
  }, []);

  useEffect(() => {
    const runId = run?.id;
    if (!runId || !active) return undefined;
    const generation = ++streamGeneration.current;
    let closed = false;
    let completed = false;
    /** @type {Promise<unknown>} */
    let refreshChain = Promise.resolve();
    const isCurrent = () => !closed && streamGeneration.current === generation;
    const source = new EventSource(api.validationEventUrl(runId), {
      withCredentials: true,
    });
    const refreshRun = () => {
      const request = refreshChain.then(() => api.validationRun(runId));
      refreshChain = request.catch(() => undefined);
      request
        .then((value) => {
          if (!isCurrent()) return;
          setSelection((current) =>
            current.connectionId === connectionId && current.run?.id === runId
              ? { ...current, run: value }
              : current,
          );
          if (!completed && FINISHED_STATUSES.includes(value.status)) {
            completed = true;
            source.close();
            Promise.resolve(onCompleted()).catch((error) => {
              if (isCurrent()) {
                notify(error instanceof Error ? error.message : "请求失败", "error");
              }
            });
            notify(
              value.status === "passed" ? "模型验证通过" : "模型验证失败",
              value.status === "passed" ? "success" : "error",
            );
          }
        })
        .catch((error) => {
          if (isCurrent()) {
            notify(error instanceof Error ? error.message : "请求失败", "error");
          }
        });
    };
    source.addEventListener("validation", (event) => {
      if (!isCurrent() || completed) return;
      const value = /** @type {ValidationEvent} */ (JSON.parse(event.data));
      setSelection((current) =>
        current.connectionId === connectionId && current.run?.id === runId
          ? { ...current, events: [...current.events.slice(-39), value] }
          : current,
      );
      refreshRun();
    });
    source.addEventListener("close", () => {
      if (isCurrent() && !completed) refreshRun();
    });
    return () => {
      closed = true;
      source.close();
    };
  }, [active, connectionId, notify, onCompleted, run?.id]);

  useEffect(() => {
    if (!active || !startedAt) return undefined;
    const updateElapsed = () => {
      const started = new Date(startedAt).getTime();
      setElapsed(
        Number.isNaN(started) ? 0 : Math.max(0, (Date.now() - started) / 1000),
      );
    };
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 200);
    return () => window.clearInterval(timer);
  }, [active, startedAt]);

  return { run, events, elapsed, active, showRun, clearRun };
}
