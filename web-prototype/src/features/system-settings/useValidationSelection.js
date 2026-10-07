import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { modelApi as api } from "../../shared/api/modelApi";
/** @typedef {import("./modelServiceViewContracts").ValidationRun} ValidationRun */
/** @typedef {import("./modelServiceViewContracts").ValidationEvent} ValidationEvent */
/** @typedef {{connectionId: string | null, run: ValidationRun | null, events: ValidationEvent[]}} ValidationSelection */
/** @typedef {import("react").Dispatch<import("react").SetStateAction<ValidationSelection>>} SetSelection */
/** @typedef {import("react").RefObject<number>} Generation */
/** @typedef {(message: string, type?: "success" | "error") => void} Notify */
/** @typedef {{currentConnection: import("react").RefObject<string | null>, lookupGeneration: Generation, streamGeneration: Generation, setSelection: SetSelection, setElapsed: (value: number) => void}} SelectionControl */
/** @param {string | null} connectionId @param {Notify} notify @param {SelectionControl} control */
function lookupActiveRun(
  connectionId,
  notify,
  { lookupGeneration, streamGeneration, setSelection, setElapsed },
) {
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
}

/** @param {SelectionControl} control @param {ValidationRun} value @param {string | null} ownerId */
function showOwnedRun(
  { currentConnection, lookupGeneration, streamGeneration, setSelection },
  value,
  ownerId,
) {
  if (ownerId !== currentConnection.current) return false;
  lookupGeneration.current += 1;
  streamGeneration.current += 1;
  setSelection({ connectionId: ownerId, run: value, events: [] });
  return true;
}

/** @param {SelectionControl} control */
function clearOwnedRun({
  currentConnection,
  lookupGeneration,
  streamGeneration,
  setSelection,
  setElapsed,
}) {
  lookupGeneration.current += 1;
  streamGeneration.current += 1;
  setSelection({ connectionId: currentConnection.current, run: null, events: [] });
  setElapsed(0);
}

/** @param {string | null} connectionId @param {Notify} notify */
export function useValidationSelection(connectionId, notify) {
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
  const control = {
    currentConnection,
    lookupGeneration,
    streamGeneration,
    setSelection,
    setElapsed,
  };
  useLayoutEffect(() => {
    currentConnection.current = connectionId;
  }, [connectionId]);

  useEffect(
    () =>
      lookupActiveRun(connectionId, notify, {
        currentConnection,
        lookupGeneration,
        streamGeneration,
        setSelection,
        setElapsed,
      }),
    [connectionId, notify],
  );
  const showRun = useCallback(
    (/** @type {ValidationRun} */ value, /** @type {string | null} */ ownerId) =>
      showOwnedRun(
        {
          currentConnection,
          lookupGeneration,
          streamGeneration,
          setSelection,
          setElapsed,
        },
        value,
        ownerId,
      ),
    [],
  );
  const clearRun = useCallback(
    () =>
      clearOwnedRun({
        currentConnection,
        lookupGeneration,
        streamGeneration,
        setSelection,
        setElapsed,
      }),
    [],
  );
  return { selection, elapsed, control, showRun, clearRun };
}
