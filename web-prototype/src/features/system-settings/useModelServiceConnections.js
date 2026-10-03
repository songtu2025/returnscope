import { useCallback, useEffect, useRef, useState } from "react";
import { modelApi as modelServiceApi } from "../../shared/api/modelApi";
import { errorMessage } from "./modelServiceConfig";

/** @typedef {import("./modelServiceViewContracts").ModelConnection} ModelConnection */

/**
 * @param {{notify: (message: string, type?: "success" | "error") => void, focusConnectionId: string | null}} options
 */
export function useModelServiceConnections({ notify, focusConnectionId }) {
  const [connections, setConnections] = useState(/** @type {ModelConnection[]} */ ([]));
  const [loadState, setLoadState] = useState(
    /** @type {"loading" | "ready" | "error"} */ ("loading"),
  );
  const [loadError, setLoadError] = useState("");
  const [selectedConnectionId, setSelectedConnectionId] = useState(
    /** @type {string | null} */ (null),
  );
  const hasLoadedConnections = useRef(false);
  const loadGeneration = useRef(0);

  const load = useCallback(async () => {
    const generation = ++loadGeneration.current;
    const isInitialLoad = !hasLoadedConnections.current;
    if (isInitialLoad) {
      setLoadState("loading");
      setLoadError("");
    }
    try {
      const values = await modelServiceApi.configs();
      if (generation !== loadGeneration.current) return;
      setConnections(values);
      setSelectedConnectionId(
        (current) =>
          values.find((item) => String(item.id) === String(focusConnectionId))?.id ??
          current ??
          values[0]?.id ??
          null,
      );
      hasLoadedConnections.current = true;
      setLoadState("ready");
      setLoadError("");
    } catch (error) {
      if (generation !== loadGeneration.current) return;
      if (isInitialLoad) {
        setLoadState("error");
        setLoadError(errorMessage(error));
      }
      throw error;
    }
  }, [focusConnectionId]);
  useEffect(() => {
    load().catch((error) => notify(errorMessage(error), "error"));
    return () => {
      loadGeneration.current += 1;
    };
  }, [load, notify]);
  const selectedConnection = connections.find(
    (item) => item.id === selectedConnectionId,
  );
  const draftVersion = selectedConnection?.versions?.find(
    (version) =>
      version.id !== selectedConnection.active_version_id && !version.published_at,
  );
  const activeVersion = selectedConnection?.active_version ?? null;
  return {
    connections,
    setConnections,
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
