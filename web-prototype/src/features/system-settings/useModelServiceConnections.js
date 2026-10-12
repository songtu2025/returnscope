import { useDataRefresh } from "../../hooks/useDataRefresh";
import { useProtectedData } from "../../hooks/useProtectedData";
import { useCallback, useEffect, useRef, useState } from "react";
import { modelApi as modelServiceApi } from "../../shared/api/modelApi";
import { errorMessage } from "./modelServiceConfig";

/** @typedef {import("./modelServiceViewContracts").ModelConnection} ModelConnection */

/**
 * @param {{notify: (message: string, type?: "success" | "error") => void, focusConnectionId: string | null}} options
 */
export function useModelServiceConnections({ notify, focusConnectionId }) {
  const [connections, setFetchedConnections] = useState(
    /** @type {ModelConnection[]} */ ([]),
  );
  const [localRevision, setLocalRevision] = useState(0);
  const setConnections = useCallback(
    /** @param {import("react").SetStateAction<ModelConnection[]>} value */
    (value) => {
      setFetchedConnections(value);
      setLocalRevision((revision) => revision + 1);
    },
    [],
  );
  const [loadState, setLoadState] = useState(
    /** @type {"loading" | "ready" | "error"} */ ("loading"),
  );
  const [loadError, setLoadError] = useState("");
  const [selectedConnectionId, setSelectedConnectionId] = useState(
    /** @type {string | null} */ (null),
  );
  const [protectedOperation, setProtectedOperationState] = useState(false);
  const protectedRef = useRef(false);
  const setProtectedOperation = useCallback((/** @type {boolean} */ value) => {
    protectedRef.current = value;
    setProtectedOperationState(value);
  }, []);
  const hasLoadedConnections = useRef(false);
  const loadGeneration = useRef(0);

  const load = useCallback(
    async (background = false) => {
      const generation = ++loadGeneration.current;
      const isInitialLoad = !hasLoadedConnections.current;
      if (isInitialLoad) {
        setLoadState("loading");
        setLoadError("");
      }
      try {
        const values = await modelServiceApi.configs();
        if (generation !== loadGeneration.current) return;
        setFetchedConnections(values);
        if (!background) setLocalRevision((revision) => revision + 1);
        setSelectedConnectionId((current) =>
          background && protectedRef.current
            ? current
            : (values.find((item) => String(item.id) === String(focusConnectionId))
                ?.id ??
              current ??
              values[0]?.id ??
              null),
        );
        hasLoadedConnections.current = true;
        setLoadState("ready");
        setLoadError("");
      } catch (error) {
        if (generation !== loadGeneration.current) return;
        if (isInitialLoad) setLoadState("error");
        setLoadError(errorMessage(error));
        throw error;
      }
    },
    [focusConnectionId],
  );
  useEffect(() => {
    load().catch((error) => notify(errorMessage(error), "error"));
    return () => {
      loadGeneration.current += 1;
    };
  }, [load, notify]);
  useDataRefresh(() => load(true), {
    loading: loadState === "loading",
    domains: ["settings"],
  });
  const displayed = useProtectedData(
    connections,
    protectedOperation,
    `${selectedConnectionId}:${localRevision}`,
  );
  const selectedConnection = displayed.find((item) => item.id === selectedConnectionId);
  const draftVersion = selectedConnection?.versions?.find(
    (version) =>
      version.id !== selectedConnection.active_version_id && !version.published_at,
  );
  const activeVersion = selectedConnection?.active_version ?? null;
  return {
    connections: displayed,
    setConnections,
    setProtectedOperation,
    selectedConnectionId,
    setSelectedConnectionId,
    selectedConnection,
    draftVersion,
    activeVersion,
    load,
    loadState,
    loadError,
  };
}
