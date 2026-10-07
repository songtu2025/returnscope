import { modelApi as api } from "../../shared/api/modelApi";
/** @typedef {import("./modelServiceViewContracts").ValidationRun} ValidationRun */
/** @typedef {import("./modelServiceViewContracts").ValidationEvent} ValidationEvent */
/** @typedef {{connectionId: string | null, run: ValidationRun | null, events: ValidationEvent[]}} ValidationSelection */
/** @typedef {import("react").Dispatch<import("react").SetStateAction<ValidationSelection>>} SetSelection */
/** @typedef {import("react").RefObject<number>} Generation */
/** @typedef {(message: string, type?: "success" | "error") => void} Notify */
const FINISHED_STATUSES = ["passed", "failed"];
/** @typedef {{runId: string, connectionId: string | null, notify: Notify, onCompleted: () => Promise<void>, streamGeneration: Generation, setSelection: SetSelection}} StreamOptions */
/** @param {{source: EventSource, isCurrent: () => boolean, onCompleted: () => Promise<void>, notify: Notify}} context @param {ValidationRun} value */
function announceCompletion({ source, isCurrent, onCompleted, notify }, value) {
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

/** @param {StreamOptions} options */
function createValidationStream({
  runId,
  connectionId,
  notify,
  onCompleted,
  streamGeneration,
  setSelection,
}) {
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
          announceCompletion({ source, isCurrent, onCompleted, notify }, value);
        }
      })
      .catch((error) => {
        if (isCurrent()) {
          notify(error instanceof Error ? error.message : "请求失败", "error");
        }
      });
  };
  return {
    source,
    isCurrent,
    refreshRun,
    get completed() {
      return completed;
    },
    close() {
      closed = true;
      source.close();
    },
  };
}

/** @param {StreamOptions} options */
export function subscribeModelValidationRun(options) {
  const { runId, connectionId, setSelection } = options;
  const stream = createValidationStream(options);
  const { source, isCurrent, refreshRun } = stream;
  source.addEventListener("validation", (event) => {
    if (!isCurrent() || stream.completed) return;
    const value = /** @type {ValidationEvent} */ (JSON.parse(event.data));
    setSelection((current) =>
      current.connectionId === connectionId && current.run?.id === runId
        ? { ...current, events: [...current.events.slice(-39), value] }
        : current,
    );
    refreshRun();
  });
  source.addEventListener("close", () => {
    if (isCurrent() && !stream.completed) refreshRun();
  });
  return () => stream.close();
}
