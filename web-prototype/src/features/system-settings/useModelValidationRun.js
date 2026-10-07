import { useEffect } from "react";
import { useValidationSelection } from "./useValidationSelection";
import { subscribeModelValidationRun } from "./modelValidationStream";
const ACTIVE_STATUSES = ["queued", "running"];
/**
 * @param {object} options
 * @param {string | null} options.connectionId
 * @param {(message: string, type?: "success" | "error") => void} options.notify
 * @param {() => Promise<void>} options.onCompleted
 */
export function useModelValidationRun({ connectionId, notify, onCompleted }) {
  const { selection, elapsed, control, showRun, clearRun } = useValidationSelection(
    connectionId,
    notify,
  );
  const { streamGeneration, setSelection, setElapsed } = control;
  const run = selection.connectionId === connectionId ? selection.run : null;
  const events = selection.connectionId === connectionId ? selection.events : [];
  const active = Boolean(run && ACTIVE_STATUSES.includes(run.status));
  const startedAt = run?.started_at ?? run?.created_at ?? null;

  useEffect(() => {
    const runId = run?.id;
    if (!runId || !active) return undefined;
    return subscribeModelValidationRun({
      runId,
      connectionId,
      notify,
      onCompleted,
      streamGeneration,
      setSelection,
    });
  }, [
    active,
    connectionId,
    notify,
    onCompleted,
    run?.id,
    streamGeneration,
    setSelection,
  ]);
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
  }, [active, startedAt, setElapsed]);

  return { run, events, elapsed, active, showRun, clearRun };
}
