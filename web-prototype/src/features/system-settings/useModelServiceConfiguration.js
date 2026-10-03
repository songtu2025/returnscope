import { useEffect, useRef, useState } from "react";
import { modelApi as modelServiceApi } from "../../shared/api/modelApi";
import {
  EMPTY_MODEL_SERVICE_FORM,
  createModelOptions,
  errorMessage,
  formForVersion,
  getConfigFormState,
  getConfigVersionState,
  preferredVersion,
} from "./modelServiceConfig";

/** @typedef {import("./modelServiceViewContracts").ActivePanel} ActivePanel */
/** @typedef {import("./modelServiceViewContracts").ModelServiceForm} ModelServiceForm */
/** @typedef {import("./modelServiceViewContracts").ConfigVersion} ConfigVersion */
/** @typedef {import("./modelServiceViewContracts").CatalogModel} CatalogModel */
/** @typedef {import("./modelServiceViewContracts").PipelineModelKey} PipelineModelKey */
/** @typedef {import("./modelServiceViewContracts").PipelineEffortKey} PipelineEffortKey */

/**
 * @param {object} options
 * @param {ReturnType<typeof import("./useModelServiceConnections").useModelServiceConnections>} options.connectionState
 * @param {(message: string, type?: "success" | "error") => void} options.notify
 * @param {CatalogModel[]} options.draftModels
 * @param {import("react").Dispatch<import("react").SetStateAction<CatalogModel[]>>} options.setDraftModels
 * @param {string} options.busy
 * @param {(busy: string) => void} options.setBusy
 * @param {string | null} options.focusConfigVersionId
 * @param {string | null} options.focusModelId
 */
export function useModelServiceConfiguration({
  connectionState,
  notify,
  draftModels,
  setDraftModels,
  busy,
  setBusy,
  focusConfigVersionId,
  focusModelId,
}) {
  const {
    connections,
    selectedConnectionId,
    setSelectedConnectionId,
    selectedConnection,
    activeVersion,
    draftVersion,
    load,
  } = connectionState;
  const [selectedVersion, setSelectedVersion] = useState(
    /** @type {ConfigVersion | null} */ (null),
  );
  const [form, setForm] = useState(
    /** @type {ModelServiceForm} */ (EMPTY_MODEL_SERVICE_FORM),
  );
  const [editing, setEditing] = useState(false);
  const [activePanel, setActivePanel] = useState(
    /** @type {ActivePanel | null} */ (null),
  );
  const [discardConfirmation, setDiscardConfirmation] = useState(false);
  const preserveConfigFormRef = useRef(false);
  useEffect(() => {
    if (focusModelId) setActivePanel("models");
    else if (focusConfigVersionId) setActivePanel("versions");
    else setActivePanel(null);
  }, [focusConfigVersionId, focusModelId]);

  const catalogModels = selectedConnection?.models ?? draftModels;
  const modelOptions = createModelOptions(catalogModels, form);
  const { nameError, baseUrlError, apiKeyError, configFormErrors } = getConfigFormState(
    form,
    editing,
    Boolean(selectedConnection),
  );
  const saveDisabled = Boolean(busy) || configFormErrors.length > 0;
  useEffect(() => {
    if (preserveConfigFormRef.current) {
      preserveConfigFormRef.current = false;
      return;
    }
    if (!selectedConnection) return;
    const value = preferredVersion(
      selectedConnection,
      selectedVersion?.id,
      focusConfigVersionId,
    );
    setSelectedVersion(value);
    if (value) setForm(formForVersion(selectedConnection, value));
    setEditing(false);
  }, [
    connections,
    focusConfigVersionId,
    selectedConnection,
    selectedConnectionId,
    selectedVersion?.id,
  ]);
  useEffect(() => {
    setDiscardConfirmation(false);
  }, [draftVersion?.id]);
  const { previousVersion, versionChanges, selectedVersionIsActive } =
    getConfigVersionState(selectedConnection, selectedVersion);
  /** @param {ConfigVersion} value */
  const showVersion = (value) => {
    if (!selectedConnection) return;
    setSelectedVersion(value);
    setForm(formForVersion(selectedConnection, value));
    setEditing(false);
  };
  const openNewConnection = () => {
    setSelectedConnectionId(null);
    setSelectedVersion(null);
    setForm(EMPTY_MODEL_SERVICE_FORM);
    setDraftModels([]);
    setEditing(true);
    setActivePanel("connection");
  };
  const closePanel = () => {
    if (selectedVersion) showVersion(selectedVersion);
    setActivePanel(null);
  };
  /**
   * @param {ActivePanel} panel
   * @param {ConfigVersion | null} [baseVersion]
   */
  const beginConfigEdit = (panel, baseVersion = null) => {
    const value =
      baseVersion ??
      draftVersion ??
      selectedConnection?.active_version ??
      selectedVersion;
    if (value) {
      setSelectedVersion(value);
      setForm(formForVersion(selectedConnection, value, true));
    }
    setEditing(true);
    setActivePanel(panel);
  };
  const openModelCatalog = () => {
    if (activeVersion) showVersion(activeVersion);
    setActivePanel("models");
  };
  const cancelEdit = () => {
    const value = draftVersion ?? selectedConnection?.active_version ?? selectedVersion;
    if (value) showVersion(value);
    else {
      setEditing(false);
      setActivePanel(null);
    }
  };

  const save = async () => {
    setBusy("save");
    try {
      const value = await modelServiceApi.createConfig({
        ...form,
        connection_id: selectedConnection?.id ?? null,
        models: selectedConnection
          ? undefined
          : draftModels.map((model) => ({
              model_key: model.model_key,
              display_name: model.display_name,
              supported_efforts: model.supported_efforts,
              active: model.active,
            })),
      });
      setSelectedVersion(value);
      setEditing(false);
      await load();
      notify(`配置 #${value.version} 草稿已保存`);
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
    }
  };
  /** @param {ConfigVersion | null} [version] */
  const publishVersion = async (version = selectedVersion) => {
    if (!version) return;
    setBusy("publish");
    try {
      await modelServiceApi.publishConfig(version.id);
      await load();
      notify(`配置 #${version.version} 已发布`);
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
    }
  };
  const publish = () => publishVersion(selectedVersion);
  const discardDraft = async () => {
    if (!draftVersion) return;
    setBusy("discard-draft");
    try {
      await modelServiceApi.discardConfig(draftVersion.id);
      await load();
      notify(`草稿 #${draftVersion.version} 已放弃`);
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
      setDiscardConfirmation(false);
    }
  };

  /**
   * @param {PipelineModelKey} modelKey
   * @param {PipelineEffortKey} effortKey
   * @param {string} value
   */
  const selectPipelineModel = (modelKey, effortKey, value) => {
    const model = modelOptions.find((item) => item.model_key === value);
    const supportedEfforts = model?.supported_efforts ?? ["low", "medium", "high"];
    setForm({
      ...form,
      [modelKey]: value,
      [effortKey]: supportedEfforts.includes(form[effortKey])
        ? form[effortKey]
        : (supportedEfforts[0] ?? form[effortKey]),
    });
  };

  /** @param {ConfigVersion} version */
  const createDraftFromVersion = (version) => beginConfigEdit("connection", version);

  return {
    form,
    setForm,
    editing,
    activePanel,
    setActivePanel,
    selectedVersion,
    preserveConfigFormRef,
    discardConfirmation,
    setDiscardConfirmation,
    showVersion,
    nameError,
    baseUrlError,
    apiKeyError,
    configFormErrors,
    saveDisabled,
    previousVersion,
    versionChanges,
    selectedVersionIsActive,
    modelOptions,
    openNewConnection,
    closePanel,
    openModelCatalog,
    beginConfigEdit,
    cancelEdit,
    save,
    publish,
    publishVersion,
    discardDraft,
    selectPipelineModel,
    createDraftFromVersion,
  };
}
