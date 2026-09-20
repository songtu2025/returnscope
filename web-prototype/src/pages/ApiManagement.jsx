import { useCallback, useEffect, useRef, useState } from "react";
import { WarningCircle } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { api } from "../api";
import { AntdProvider } from "../components/AntdProvider";
import { EmptyState, InlineLoading, PageHeading } from "../components/SharedUi";
import { ModelEditorDialog } from "../features/system-settings/ModelEditorDialog";
import { ModelServiceEditor } from "../features/system-settings/ModelServiceEditor";
import { ModelServiceSummary } from "../features/system-settings/ModelServiceSummary";
import {
  CONFIG_DIFF_FIELDS,
  createDefaultModelCatalog,
  createModelOptions,
  EMPTY_MODEL_SERVICE_FORM,
  getBaseUrlError,
} from "../features/system-settings/modelServiceConfig";

/** @typedef {import("../shared/api/systemSettingsContracts").ActivePanel} ActivePanel */
/** @typedef {import("../shared/api/systemSettingsContracts").ModelEditorMode} ModelEditorMode */
/** @typedef {import("../shared/api/systemSettingsContracts").PipelineModelKey} PipelineModelKey */
/** @typedef {import("../shared/api/systemSettingsContracts").PipelineEffortKey} PipelineEffortKey */
/** @typedef {import("../shared/api/systemSettingsContracts").ModelServiceForm} ModelServiceForm */
/** @typedef {import("../shared/api/systemSettingsContracts").CatalogModel} CatalogModel */
/** @typedef {import("../shared/api/systemSettingsContracts").ModelDraft} ModelDraft */
/** @typedef {import("../shared/api/systemSettingsContracts").ConfigVersion} ConfigVersion */
/** @typedef {import("../shared/api/systemSettingsContracts").ModelConnection} ModelConnection */
/** @typedef {import("../shared/api/systemSettingsContracts").ValidationRun} ValidationRun */
/** @typedef {import("../shared/api/systemSettingsContracts").ValidationEvent} ValidationEvent */

/**
 * 当前页面消费的模型服务 API 契约。这里只补静态边界，不改变运行时响应处理。
 * @type {{
 *   configs: () => Promise<ModelConnection[]>,
 *   activeValidation: (connectionId: string) => Promise<ValidationRun | null>,
 *   validationRun: (runId: string) => Promise<ValidationRun>,
 *   validationEventUrl: (runId: string) => string,
 *   createConfig: (payload: object) => Promise<ConfigVersion>,
 *   startConfigValidation: (versionId: string) => Promise<ValidationRun>,
 *   publishConfig: (versionId: string) => Promise<unknown>,
 *   discardConfig: (versionId: string) => Promise<unknown>,
 *   createModel: (connectionId: string, payload: object) => Promise<CatalogModel>,
 *   updateModel: (modelId: string, payload: object) => Promise<CatalogModel>,
 *   startModelValidation: (modelId: string) => Promise<ValidationRun>,
 *   discoverModels: (connectionId: string) => Promise<{count: number}>
 * }}
 */
const modelServiceApi = api;

/** @param {unknown} error */
function errorMessage(error) {
  return error instanceof Error ? error.message : "请求失败";
}

/**
 * @param {ConfigVersion} left
 * @param {ConfigVersion | null} right
 * @param {string} key
 */
function configValuesDiffer(left, right, key) {
  if (!right) return false;
  if (key === "base_url") return left.base_url !== right.base_url;
  if (key === "requests_per_minute")
    return left.requests_per_minute !== right.requests_per_minute;
  if (key === "max_workers") return left.max_workers !== right.max_workers;
  if (key === "timeout_seconds") return left.timeout_seconds !== right.timeout_seconds;
  return false;
}

/**
 * @param {object} props
 * @param {(message: string, type?: "success" | "error") => void} props.notify
 * @param {string | null} [props.focusConnectionId]
 * @param {string | null} [props.focusConfigVersionId]
 * @param {string | null} [props.focusModelId]
 */

export function ApiManagement({
  notify,
  focusConnectionId = null,
  focusConfigVersionId = null,
  focusModelId = null,
}) {
  const [connections, setConnections] = useState(/** @type {ModelConnection[]} */ ([]));
  const [loadState, setLoadState] = useState(
    /** @type {"loading" | "ready" | "error"} */ ("loading"),
  );
  const [loadError, setLoadError] = useState("");
  const [selectedConnectionId, setSelectedConnectionId] = useState(
    /** @type {string | null} */ (null),
  );
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
  const [busy, setBusy] = useState("");
  const [draftModels, setDraftModels] = useState(
    /** @returns {CatalogModel[]} */ () => createDefaultModelCatalog(),
  );
  const [modelEditor, setModelEditor] = useState(
    /** @type {ModelEditorMode | null} */ (null),
  );
  const [modelDraft, setModelDraft] = useState(/** @type {ModelDraft | null} */ (null));
  const [validationRun, setValidationRun] = useState(
    /** @type {ValidationRun | null} */ (null),
  );
  const [validationEvents, setValidationEvents] = useState(
    /** @type {ValidationEvent[]} */ ([]),
  );
  const [validationElapsed, setValidationElapsed] = useState(0);
  const [discardConfirmation, setDiscardConfirmation] = useState(false);
  const hasLoadedConnections = useRef(false);
  const preserveConfigForm = useRef(false);
  const focusedModelRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  const validationActive = validationRun
    ? ["queued", "running"].includes(validationRun.status)
    : false;
  const validationStartedAt =
    validationRun?.started_at ?? validationRun?.created_at ?? null;
  useEffect(() => {
    if (focusModelId) setActivePanel("models");
    else if (focusConfigVersionId) setActivePanel("versions");
    else setActivePanel(null);
  }, [focusConfigVersionId, focusModelId]);

  const load = useCallback(async () => {
    const isInitialLoad = !hasLoadedConnections.current;
    if (isInitialLoad) {
      setLoadState("loading");
      setLoadError("");
    }
    try {
      const values = await modelServiceApi.configs();
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
      if (isInitialLoad) {
        setLoadState("error");
        setLoadError(errorMessage(error));
      }
      throw error;
    }
  }, [focusConnectionId]);
  useEffect(() => {
    load().catch((error) => notify(errorMessage(error), "error"));
  }, [load, notify]);
  const selectedConnection = connections.find(
    (item) => item.id === selectedConnectionId,
  );
  const draftVersion = selectedConnection?.versions?.find(
    (version) =>
      version.id !== selectedConnection.active_version_id && !version.published_at,
  );
  const activeVersion = selectedConnection?.active_version ?? null;
  const catalogModels = selectedConnection?.models ?? draftModels;
  const visibleCatalogModels = catalogModels.filter((model) => model.active);
  const availableModelCount = catalogModels.filter(
    (model) => model.active && model.validation_status === "validated",
  ).length;
  const modelOptions = createModelOptions(catalogModels, form);
  const nameError = editing && !form.name?.trim() ? "请填写接入名称。" : "";
  const baseUrlError = editing ? getBaseUrlError(form.base_url) : "";
  const apiKeyError =
    editing && !selectedConnection && !form.api_key?.trim() ? "请填写 API 密钥。" : "";
  const configFormErrors = editing
    ? [
        nameError,
        baseUrlError,
        apiKeyError,
        !form.primary_model ? "请选择验证模型。" : "",
        !form.change_note?.trim() ? "请填写配置变更原因。" : "",
      ].filter(Boolean)
    : [];
  const saveDisabled = busy === "save" || configFormErrors.length > 0;
  useEffect(() => {
    if (preserveConfigForm.current) {
      preserveConfigForm.current = false;
      return;
    }
    if (!selectedConnection) return;
    const preserved = selectedConnection?.versions?.find(
      (version) => version.id === selectedVersion?.id,
    );
    const value =
      selectedConnection?.versions?.find(
        (version) => String(version.id) === String(focusConfigVersionId),
      ) ??
      preserved ??
      selectedConnection?.versions?.find(
        (version) =>
          version.id !== selectedConnection.active_version_id && !version.published_at,
      ) ??
      selectedConnection?.active_version ??
      selectedConnection?.versions?.[0] ??
      null;
    setSelectedVersion(value);
    if (value)
      setForm({
        ...EMPTY_MODEL_SERVICE_FORM,
        ...value,
        name: selectedConnection.name,
        api_key: "",
        connection_id: selectedConnection.id,
      });
    setEditing(false);
  }, [
    connections,
    focusConfigVersionId,
    selectedConnection,
    selectedConnectionId,
    selectedVersion?.id,
  ]);
  useEffect(() => {
    if (!focusModelId || !focusedModelRef.current) return;
    focusedModelRef.current.scrollIntoView({ block: "center" });
  }, [catalogModels, focusModelId, selectedConnectionId]);
  useEffect(() => {
    let cancelled = false;
    if (!selectedConnectionId) {
      setValidationRun(null);
      setValidationEvents([]);
      return undefined;
    }
    setValidationRun(null);
    setValidationEvents([]);
    modelServiceApi
      .activeValidation(selectedConnectionId)
      .then((value) => {
        if (!cancelled && value) {
          setValidationRun(value);
          setValidationEvents([]);
        }
      })
      .catch((error) => notify(errorMessage(error), "error"));
    return () => {
      cancelled = true;
    };
  }, [selectedConnectionId, notify]);
  useEffect(() => {
    setDiscardConfirmation(false);
  }, [draftVersion?.id]);
  useEffect(() => {
    const runId = validationRun?.id;
    if (!runId || !validationActive) return undefined;
    let closed = false;
    /** @type {Promise<void | ValidationRun>} */
    let refreshChain = Promise.resolve();
    const refreshRun = () => {
      refreshChain = refreshChain
        .then(() => modelServiceApi.validationRun(runId))
        .then((value) => {
          if (!closed) setValidationRun(value);
          return value;
        });
      return refreshChain;
    };
    const source = new EventSource(modelServiceApi.validationEventUrl(runId), {
      withCredentials: true,
    });
    source.addEventListener("validation", (event) => {
      const value = /** @type {ValidationEvent} */ (JSON.parse(event.data));
      setValidationEvents((current) => [...current.slice(-39), value]);
      refreshRun();
    });
    source.addEventListener("close", () => {
      source.close();
      refreshRun().then((value) => {
        if (closed || !value) return;
        load();
        notify(
          value.status === "passed" ? "模型验证通过" : "模型验证失败",
          value.status === "passed" ? "success" : "error",
        );
      });
    });
    return () => {
      closed = true;
      source.close();
    };
  }, [load, notify, validationActive, validationRun?.id]);
  useEffect(() => {
    if (!validationActive || !validationStartedAt) return undefined;
    const updateElapsed = () => {
      const started = new Date(validationStartedAt).getTime();
      setValidationElapsed(
        Number.isNaN(started) ? 0 : Math.max(0, (Date.now() - started) / 1000),
      );
    };
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 200);
    return () => window.clearInterval(timer);
  }, [validationActive, validationStartedAt]);
  const previousVersion = selectedConnection?.versions?.find(
    (version) => version.version === (selectedVersion?.version ?? 1) - 1,
  );
  const versionChanges = previousVersion
    ? CONFIG_DIFF_FIELDS.filter(([key]) =>
        configValuesDiffer(previousVersion, selectedVersion, key),
      )
    : [];
  const selectedVersionIsActive =
    selectedConnection?.active_version_id === selectedVersion?.id;
  /** @param {ConfigVersion} value */
  const showVersion = (value) => {
    if (!selectedConnection) return;
    setSelectedVersion(value);
    setForm({
      ...EMPTY_MODEL_SERVICE_FORM,
      ...value,
      name: selectedConnection.name,
      api_key: "",
      connection_id: selectedConnection.id,
    });
    setEditing(false);
  };
  const openNewConnection = () => {
    setSelectedConnectionId(null);
    setSelectedVersion(null);
    setForm(EMPTY_MODEL_SERVICE_FORM);
    setDraftModels(createDefaultModelCatalog());
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
      setForm({
        ...EMPTY_MODEL_SERVICE_FORM,
        ...value,
        name: selectedConnection?.name ?? "",
        api_key: "",
        connection_id: selectedConnection?.id,
        change_note: "",
      });
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
  /** @param {ValidationRun} value */
  const showValidationRun = (value) => {
    setValidationRun(value);
    setValidationEvents([]);
    window.requestAnimationFrame(() =>
      document
        .getElementById("validation-process")
        ?.scrollIntoView({ behavior: "smooth", block: "center" }),
    );
  };
  /** @param {ConfigVersion | null} [version] */
  const startValidation = async (version = selectedVersion) => {
    if (!version) return;
    showVersion(version);
    setActivePanel("models");
    setBusy("validation-start");
    try {
      const value = await modelServiceApi.startConfigValidation(version.id);
      showValidationRun(value);
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
    }
  };
  const validate = () => startValidation(selectedVersion);
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

  /** @param {CatalogModel | null} [model] */
  const openModelEditor = (model = null) => {
    setModelEditor(model ? "edit" : "create");
    setModelDraft(
      model
        ? {
            ...model,
            supported_efforts: [...model.supported_efforts],
          }
        : {
            model_key: "",
            display_name: "",
            supported_efforts: ["low", "medium", "high"],
            active: true,
          },
    );
  };

  const closeModelEditor = () => {
    if (busy === "model-save") return;
    setModelEditor(null);
    setModelDraft(null);
  };

  /**
   * @param {CatalogModel} value
   * @param {boolean} [append]
   */
  const mergeModel = (value, append = false) => {
    preserveConfigForm.current = editing;
    setConnections((current) =>
      current.map((connection) =>
        connection.id === value.connection_id
          ? {
              ...connection,
              models: append
                ? [...(connection.models ?? []), value]
                : (connection.models ?? []).map((model) =>
                    model.id === value.id ? value : model,
                  ),
            }
          : connection,
      ),
    );
  };

  const saveModel = async () => {
    if (!modelDraft) return;
    const modelKey = modelDraft.model_key.trim();
    if (!modelKey) {
      notify("请填写模型 ID", "error");
      return;
    }
    if (!modelDraft.supported_efforts.length) {
      notify("至少选择一种推理强度", "error");
      return;
    }
    const modelId = modelDraft.id;
    if (modelEditor !== "create" && !modelId) {
      notify("模型数据无效", "error");
      return;
    }
    if (
      modelEditor === "create" &&
      catalogModels.some((model) => model.model_key === modelKey)
    ) {
      notify("该模型 ID 已存在", "error");
      return;
    }
    const payload = {
      model_key: modelKey,
      display_name: modelDraft.display_name.trim() || modelKey,
      supported_efforts: modelDraft.supported_efforts,
      active: modelDraft.active,
    };
    setBusy("model-save");
    try {
      if (!selectedConnection) {
        if (modelEditor === "create") {
          setDraftModels((current) => [
            ...current,
            {
              ...payload,
              id: `draft-${modelKey}`,
              validation_status: "draft",
            },
          ]);
        } else {
          setDraftModels((current) =>
            current.map((model) =>
              model.id === modelDraft.id ? { ...model, ...payload } : model,
            ),
          );
        }
      } else if (modelEditor === "create") {
        const value = await modelServiceApi.createModel(selectedConnection.id, payload);
        mergeModel(value, true);
      } else {
        if (!modelId) return;
        const value = await modelServiceApi.updateModel(modelId, {
          display_name: payload.display_name,
          supported_efforts: payload.supported_efforts,
          active: payload.active,
        });
        mergeModel(value);
      }
      setModelEditor(null);
      setModelDraft(null);
      notify(modelEditor === "create" ? "模型已添加" : "模型已更新");
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
    }
  };

  /** @param {CatalogModel} model */
  const toggleModel = async (model) => {
    if (
      !selectedConnection &&
      model.active &&
      [form.cheap_model, form.primary_model, form.secondary_model].includes(
        model.model_key,
      )
    ) {
      notify("请先从模型流水线中移除该模型", "error");
      return;
    }
    if (!selectedConnection) {
      setDraftModels((current) =>
        current.map((item) =>
          item.id === model.id ? { ...item, active: !item.active } : item,
        ),
      );
      return;
    }
    setBusy(`model-toggle-${model.id}`);
    try {
      const value = await modelServiceApi.updateModel(model.id, {
        display_name: model.display_name,
        supported_efforts: model.supported_efforts,
        active: !model.active,
      });
      mergeModel(value);
      notify(model.active ? "模型已停用" : "模型已启用");
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
    }
  };

  /** @param {CatalogModel} model */
  const validateCatalogModel = async (model) => {
    setBusy("validation-start");
    try {
      const value = await modelServiceApi.startModelValidation(model.id);
      showValidationRun(value);
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
    }
  };

  const discoverModels = async () => {
    if (!selectedConnection) return;
    setBusy("model-discover");
    try {
      const value = await modelServiceApi.discoverModels(selectedConnection.id);
      await load();
      notify(`已读取 ${value.count} 个接入方模型；目录外模型已停用`, "success");
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
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

  return (
    <AntdProvider>
      <div className="standard-page api-page">
        <PageHeading
          eyebrow="共享系统配置"
          title="模型服务"
          description="维护共享接入、模型可用性与运行限制；个人策略与任务选择在各自页面保存。"
          action={
            activePanel ? (
              <Button autoInsertSpace={false} onClick={closePanel}>
                返回服务摘要
              </Button>
            ) : null
          }
        />
        {loadState === "loading" ? (
          <InlineLoading label="正在读取模型服务…" />
        ) : loadState === "error" ? (
          <section role="alert">
            <EmptyState
              icon={WarningCircle}
              title="模型服务读取失败"
              description={loadError}
              action={
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() =>
                    load().catch((error) => notify(errorMessage(error), "error"))
                  }
                >
                  重新加载
                </button>
              }
            />
          </section>
        ) : !activePanel ? (
          <ModelServiceSummary
            connections={connections}
            selectedConnectionId={selectedConnectionId}
            selectedConnection={selectedConnection}
            activeVersion={activeVersion}
            availableModelCount={availableModelCount}
            busy={busy}
            validationActive={validationActive}
            draftVersion={draftVersion}
            discardConfirmation={discardConfirmation}
            visibleCatalogModels={visibleCatalogModels}
            onSelectConnection={setSelectedConnectionId}
            onStartValidation={startValidation}
            onOpenNewConnection={openNewConnection}
            onEditConnection={() => beginConfigEdit("connection")}
            onEditLimits={() => beginConfigEdit("limits")}
            onOpenVersions={() => setActivePanel("versions")}
            onCancelDiscard={() => setDiscardConfirmation(false)}
            onDiscardDraft={discardDraft}
            onPublishDraft={() => publishVersion(draftVersion)}
            onContinueDraft={() => beginConfigEdit("connection")}
            onConfirmDiscard={() => setDiscardConfirmation(true)}
            onDiscoverModels={discoverModels}
            onOpenModelCatalog={openModelCatalog}
            onValidateCatalogModel={validateCatalogModel}
          />
        ) : (
          <ModelServiceEditor
            activePanel={activePanel}
            connections={connections}
            selectedConnectionId={selectedConnectionId}
            onSelectConnection={setSelectedConnectionId}
            selectedVersion={selectedVersion}
            selectedConnection={selectedConnection}
            editing={editing}
            validationActive={validationActive}
            busy={busy}
            onBeginEdit={beginConfigEdit}
            form={form}
            onFormChange={setForm}
            nameError={nameError}
            baseUrlError={baseUrlError}
            apiKeyError={apiKeyError}
            catalogModels={catalogModels}
            focusModelId={focusModelId}
            focusedModelRef={focusedModelRef}
            onCloseValidation={() => {
              setValidationRun(null);
              setValidationEvents([]);
            }}
            onOpenModelEditor={openModelEditor}
            onPublish={publish}
            onToggleModel={toggleModel}
            onValidateModel={validateCatalogModel}
            selectedVersionIsActive={selectedVersionIsActive}
            validationElapsed={validationElapsed}
            validationEvents={validationEvents}
            validationRun={validationRun}
            modelOptions={modelOptions}
            onSelectPipelineModel={selectPipelineModel}
            configFormErrors={configFormErrors}
            onCancelEdit={cancelEdit}
            onSave={save}
            saveDisabled={saveDisabled}
            onValidate={validate}
            previousVersion={previousVersion}
            versionChanges={versionChanges}
            onShowVersion={showVersion}
            onCreateDraft={createDraftFromVersion}
          />
        )}
      </div>
      <ModelEditorDialog
        busy={busy}
        editorMode={modelEditor}
        modelDraft={modelDraft}
        onChange={setModelDraft}
        onClose={closeModelEditor}
        onSave={saveModel}
      />
    </AntdProvider>
  );
}
