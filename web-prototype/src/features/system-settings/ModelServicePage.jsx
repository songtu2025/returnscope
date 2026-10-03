import { useEffect, useRef, useState } from "react";
import { ModelServiceView } from "./ModelServiceView";
import { useModelServiceConnections } from "./useModelServiceConnections";
import { useModelServiceConfiguration } from "./useModelServiceConfiguration";
import { useModelServiceCatalog } from "./useModelServiceCatalog";
import { useModelValidationRun } from "./useModelValidationRun";
import { modelApi as modelServiceApi } from "../../shared/api/modelApi";
import { errorMessage } from "./modelServiceConfig";

/** @typedef {import("./modelServiceViewContracts").CatalogModel} CatalogModel */
/** @typedef {import("./modelServiceViewContracts").ConfigVersion} ConfigVersion */
/** @typedef {import("./modelServiceViewContracts").ValidationRun} ValidationRun */

/**
 * @param {object} props
 * @param {(message: string, type?: "success" | "error") => void} props.notify
 * @param {string | null} [props.focusConnectionId]
 * @param {string | null} [props.focusConfigVersionId]
 * @param {string | null} [props.focusModelId]
 */
export function ModelServicePage({
  notify,
  focusConnectionId = null,
  focusConfigVersionId = null,
  focusModelId = null,
}) {
  const [busy, setBusy] = useState("");
  const [draftModels, setDraftModels] = useState(/** @type {CatalogModel[]} */ ([]));
  const focusedModelRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const connectionState = useModelServiceConnections({ notify, focusConnectionId });
  const configuration = useModelServiceConfiguration({
    connectionState,
    notify,
    draftModels,
    setDraftModels,
    busy,
    setBusy,
    focusConfigVersionId,
    focusModelId,
  });
  const validation = useModelValidationRun({
    connectionId: connectionState.selectedConnectionId,
    notify,
    onCompleted: connectionState.load,
  });
  const { selectedConnectionId } = connectionState;
  const { selectedVersion, showVersion, setActivePanel } = configuration;
  const { showRun } = validation;
  /**
   * @param {ValidationRun} value
   * @param {string | null} ownerId
   */
  const showValidationRun = (value, ownerId) => {
    if (!showRun(value, ownerId)) return;
    window.requestAnimationFrame(() =>
      document
        .getElementById("validation-process")
        ?.scrollIntoView({ behavior: "smooth", block: "center" }),
    );
  };
  /** @param {ConfigVersion | null} [version] */
  const startValidation = async (version = selectedVersion) => {
    if (!version) return;
    const ownerId = selectedConnectionId;
    showVersion(version);
    setActivePanel("models");
    setBusy("validation-start");
    try {
      const value = await modelServiceApi.startConfigValidation(version.id);
      showValidationRun(value, ownerId);
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
    }
  };
  const catalog = useModelServiceCatalog({
    connectionState,
    configuration,
    notify,
    draftModels,
    setDraftModels,
    busy,
    setBusy,
    showValidationRun,
  });
  const { catalogModels } = catalog;
  useEffect(() => {
    if (!focusModelId || !focusedModelRef.current) return;
    focusedModelRef.current.scrollIntoView({ block: "center" });
  }, [catalogModels, focusModelId, selectedConnectionId]);
  return (
    <ModelServiceView
      connectionState={connectionState}
      configuration={configuration}
      catalog={catalog}
      validation={validation}
      startValidation={startValidation}
      busy={busy}
      focusModelId={focusModelId}
      focusedModelRef={focusedModelRef}
      notify={notify}
    />
  );
}
