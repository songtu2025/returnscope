import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  CaretDown,
  CheckCircle,
  Clock,
  Plus,
  Power,
  ShieldCheck,
  SlidersHorizontal,
  WarningCircle,
} from "@phosphor-icons/react";
import { api } from "../api";
import { CardHeading, InfoRow, Modal, PageHeading } from "../components/SharedUi";
import { EFFORT_LABELS, MODEL_STATUS_LABELS } from "../constants";
import { ModelCatalogSection } from "../features/system-settings/ModelCatalogSection";
import { classNames, formatTime } from "../lib/presentation";

const CONFIG_DIFF_FIELDS = [
  ["base_url", "Base URL"],
  ["requests_per_minute", "每分钟请求"],
  ["max_workers", "单任务并发"],
  ["timeout_seconds", "请求超时"],
];
const EMPTY_FORM = {
  name: "",
  provider: "responses-compatible",
  base_url: "",
  api_key: "",
  primary_model: "",
  primary_effort: "medium",
  cheap_model: null,
  cheap_effort: "low",
  secondary_model: null,
  secondary_effort: "high",
  cheap_audit_percent: 5,
  requests_per_minute: 60,
  max_workers: 4,
  timeout_seconds: 120,
  change_note: "",
};

function createDefaultModelCatalog() {
  return [];
}

function configValue(key, value) {
  if (key.endsWith("_effort")) return EFFORT_LABELS[value] ?? value ?? "未设置";
  return value === null || value === undefined || value === ""
    ? "未设置"
    : String(value);
}

export function ApiManagement({
  notify,
  focusConnectionId = null,
  focusConfigVersionId = null,
  focusModelId = null,
}) {
  const [connections, setConnections] = useState([]);
  const [selectedConnectionId, setSelectedConnectionId] = useState(null);
  const [selectedVersion, setSelectedVersion] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editing, setEditing] = useState(false);
  const [activePanel, setActivePanel] = useState(null);
  const [busy, setBusy] = useState("");
  const [draftModels, setDraftModels] = useState(createDefaultModelCatalog);
  const [modelEditor, setModelEditor] = useState(null);
  const [modelDraft, setModelDraft] = useState(null);
  const [validationRun, setValidationRun] = useState(null);
  const [validationEvents, setValidationEvents] = useState([]);
  const [validationElapsed, setValidationElapsed] = useState(0);
  const [discardConfirmation, setDiscardConfirmation] = useState(false);
  const preserveConfigForm = useRef(false);
  const focusedModelRef = useRef(null);
  const validationActive = ["queued", "running"].includes(validationRun?.status);
  useEffect(() => {
    if (focusModelId) setActivePanel("models");
    else if (focusConfigVersionId) setActivePanel("versions");
    else setActivePanel(null);
  }, [focusConfigVersionId, focusModelId]);

  const load = useCallback(async () => {
    const values = await api.configs();
    setConnections(values);
    setSelectedConnectionId(
      (current) =>
        values.find((item) => String(item.id) === String(focusConnectionId))?.id ??
        current ??
        values[0]?.id ??
        null,
    );
  }, [focusConnectionId]);
  useEffect(() => {
    load().catch((error) => notify(error.message, "error"));
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
  const historicalModelKeys = [
    form.cheap_model,
    form.primary_model,
    form.secondary_model,
  ].filter(Boolean);
  const modelOptions = [
    ...catalogModels,
    ...historicalModelKeys
      .filter(
        (modelKey) => !catalogModels.some((model) => model.model_key === modelKey),
      )
      .map((modelKey) => ({
        id: `historical-${modelKey}`,
        model_key: modelKey,
        display_name: modelKey,
        supported_efforts: ["low", "medium", "high"],
        active: false,
        historical: true,
      })),
  ];
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
        ...EMPTY_FORM,
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
    api
      .activeValidation(selectedConnectionId)
      .then((value) => {
        if (!cancelled && value) {
          setValidationRun(value);
          setValidationEvents([]);
        }
      })
      .catch((error) => notify(error.message, "error"));
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
    let refreshChain = Promise.resolve();
    const refreshRun = () => {
      refreshChain = refreshChain
        .then(() => api.validationRun(runId))
        .then((value) => {
          if (!closed) setValidationRun(value);
          return value;
        });
      return refreshChain;
    };
    const source = new EventSource(api.validationEventUrl(runId), {
      withCredentials: true,
    });
    source.addEventListener("validation", (event) => {
      const value = JSON.parse(event.data);
      setValidationEvents((current) => [...current.slice(-39), value]);
      refreshRun();
    });
    source.addEventListener("close", () => {
      source.close();
      refreshRun().then((value) => {
        if (closed) return;
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
    if (!validationActive) return undefined;
    const startedAt = validationRun.started_at ?? validationRun.created_at;
    const updateElapsed = () => {
      const started = new Date(startedAt).getTime();
      setValidationElapsed(
        Number.isNaN(started) ? 0 : Math.max(0, (Date.now() - started) / 1000),
      );
    };
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 200);
    return () => window.clearInterval(timer);
  }, [validationActive, validationRun?.created_at, validationRun?.started_at]);
  const previousVersion = selectedConnection?.versions?.find(
    (version) => version.version === (selectedVersion?.version ?? 1) - 1,
  );
  const versionChanges = previousVersion
    ? CONFIG_DIFF_FIELDS.filter(
        ([key]) => previousVersion[key] !== selectedVersion?.[key],
      )
    : [];
  const selectedVersionIsActive =
    selectedConnection?.active_version_id === selectedVersion?.id;
  const showVersion = (value) => {
    setSelectedVersion(value);
    setForm({
      ...EMPTY_FORM,
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
    setForm(EMPTY_FORM);
    setDraftModels(createDefaultModelCatalog());
    setEditing(true);
    setActivePanel("connection");
  };
  const closePanel = () => {
    if (selectedVersion) showVersion(selectedVersion);
    setActivePanel(null);
  };
  const beginConfigEdit = (panel, baseVersion = null) => {
    const value =
      baseVersion ??
      draftVersion ??
      selectedConnection?.active_version ??
      selectedVersion;
    if (value) {
      setSelectedVersion(value);
      setForm({
        ...EMPTY_FORM,
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
      const value = await api.createConfig({
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
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  };
  const showValidationRun = (value) => {
    setValidationRun(value);
    setValidationEvents([]);
    window.requestAnimationFrame(() =>
      document
        .getElementById("validation-process")
        ?.scrollIntoView({ behavior: "smooth", block: "center" }),
    );
  };
  const startValidation = async (version = selectedVersion) => {
    if (!version) return;
    showVersion(version);
    setActivePanel("models");
    setBusy("validation-start");
    try {
      const value = await api.startConfigValidation(version.id);
      showValidationRun(value);
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  };
  const validate = () => startValidation(selectedVersion);
  const publishVersion = async (version = selectedVersion) => {
    if (!version) return;
    setBusy("publish");
    try {
      await api.publishConfig(version.id);
      await load();
      notify(`配置 #${version.version} 已发布`);
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  };
  const publish = () => publishVersion(selectedVersion);
  const discardDraft = async () => {
    if (!draftVersion) return;
    setBusy("discard-draft");
    try {
      await api.discardConfig(draftVersion.id);
      await load();
      notify(`草稿 #${draftVersion.version} 已放弃`);
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
      setDiscardConfirmation(false);
    }
  };

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
        const value = await api.createModel(selectedConnection.id, payload);
        mergeModel(value, true);
      } else {
        const value = await api.updateModel(modelDraft.id, {
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
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  };

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
      const value = await api.updateModel(model.id, {
        display_name: model.display_name,
        supported_efforts: model.supported_efforts,
        active: !model.active,
      });
      mergeModel(value);
      notify(model.active ? "模型已停用" : "模型已启用");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  };

  const validateCatalogModel = async (model) => {
    setBusy("validation-start");
    try {
      const value = await api.startModelValidation(model.id);
      showValidationRun(value);
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  };

  const discoverModels = async () => {
    if (!selectedConnection) return;
    setBusy("model-discover");
    try {
      const value = await api.discoverModels(selectedConnection.id);
      await load();
      notify(`已读取 ${value.count} 个接入方模型；目录外模型已停用`, "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  };

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

  return (
    <>
      <div className="standard-page api-page">
        <PageHeading
          eyebrow="共享系统配置"
          title="模型服务"
          description="维护共享接入、模型可用性与运行限制；个人策略与任务选择在各自页面保存。"
          action={
            activePanel ? (
              <button className="secondary-button" onClick={closePanel}>
                返回服务摘要
              </button>
            ) : null
          }
        />
        {!activePanel ? (
          <div className="model-service-summary">
            {connections.length > 1 && (
              <label className="model-service-selector">
                模型服务
                <select
                  value={selectedConnectionId ?? ""}
                  onChange={(event) => setSelectedConnectionId(event.target.value)}
                >
                  {connections.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <section className="content-card model-service-runtime">
              <div
                className={classNames(
                  "model-service-runtime-icon",
                  activeVersion?.validation_status === "validated" && "online",
                )}
              >
                {activeVersion?.validation_status === "validated" ? (
                  <CheckCircle size={36} weight="duotone" />
                ) : (
                  <WarningCircle size={36} weight="duotone" />
                )}
              </div>
              <div className="model-service-runtime-main">
                <span className="asset-type">当前接入</span>
                <div className="model-service-runtime-title">
                  <h2>{selectedConnection?.name ?? "尚未创建模型服务"}</h2>
                  <span
                    className={classNames(
                      "model-service-status",
                      activeVersion?.validation_status,
                    )}
                  >
                    {activeVersion?.validation_status === "validated"
                      ? "运行正常"
                      : activeVersion
                        ? "等待验证"
                        : "尚未发布"}
                  </span>
                </div>
                <div className="model-service-runtime-meta">
                  <span>
                    服务地址 <b>{activeVersion?.base_url ?? "—"}</b>
                  </span>
                  <span>
                    运行版本 {activeVersion ? `#${activeVersion.version}` : "—"}
                  </span>
                  <span>{availableModelCount} 个可用模型</span>
                </div>
              </div>
              <div className="model-service-runtime-actions">
                {activeVersion ? (
                  <button
                    className="primary-button"
                    onClick={() => startValidation(activeVersion)}
                    disabled={Boolean(busy) || validationActive}
                  >
                    <Power size={17} />
                    {validationActive ? "验证中…" : "验证服务"}
                  </button>
                ) : (
                  <button className="primary-button" onClick={openNewConnection}>
                    <Plus size={18} />
                    新增模型服务
                  </button>
                )}
                {selectedConnection && (
                  <button
                    className="text-button"
                    onClick={() => beginConfigEdit("connection")}
                  >
                    编辑连接
                  </button>
                )}
                {selectedConnection && (
                  <details className="model-service-more">
                    <summary role="button" aria-haspopup="menu">
                      更多 <CaretDown size={15} />
                    </summary>
                    <div
                      className="model-service-more-menu"
                      role="menu"
                      aria-label="更多模型服务操作"
                    >
                      <button
                        type="button"
                        role="menuitem"
                        onClick={() => beginConfigEdit("limits")}
                      >
                        请求限制
                      </button>
                      <button
                        type="button"
                        role="menuitem"
                        onClick={() => setActivePanel("versions")}
                      >
                        配置版本
                      </button>
                      {activeVersion && (
                        <button
                          type="button"
                          role="menuitem"
                          onClick={openNewConnection}
                        >
                          新增模型服务
                        </button>
                      )}
                    </div>
                  </details>
                )}
              </div>
            </section>
            {draftVersion && (
              <section className="model-service-draft-strip">
                <div className="model-service-draft-copy">
                  <WarningCircle size={22} weight="duotone" />
                  <p>
                    <b>
                      草稿 #{draftVersion.version} ·{" "}
                      {draftVersion.validation_status === "validated"
                        ? "可发布"
                        : draftVersion.validation_status === "failed"
                          ? "验证失败"
                          : "待验证"}
                    </b>
                    <span>
                      {draftVersion.change_note || "未填写变更说明"}；当前运行
                      {activeVersion ? ` #${activeVersion.version}` : ""} 不受影响
                    </span>
                  </p>
                </div>
                {discardConfirmation ? (
                  <div className="model-service-discard-confirmation">
                    <span>放弃后不可恢复</span>
                    <button
                      className="text-button"
                      onClick={() => setDiscardConfirmation(false)}
                      disabled={busy === "discard-draft"}
                    >
                      取消
                    </button>
                    <button
                      className="danger-button"
                      onClick={discardDraft}
                      disabled={busy === "discard-draft"}
                    >
                      {busy === "discard-draft" ? "放弃中…" : "确认放弃"}
                    </button>
                  </div>
                ) : (
                  <div className="model-service-draft-actions">
                    <button
                      className="primary-button"
                      onClick={() =>
                        draftVersion.validation_status === "validated"
                          ? publishVersion(draftVersion)
                          : beginConfigEdit("connection")
                      }
                      disabled={Boolean(busy) || validationActive}
                    >
                      {draftVersion.validation_status === "validated"
                        ? "发布版本"
                        : "继续处理"}
                    </button>
                    <button
                      className="text-button"
                      onClick={() => setDiscardConfirmation(true)}
                      disabled={Boolean(busy) || validationActive}
                    >
                      放弃草稿
                    </button>
                  </div>
                )}
              </section>
            )}
            <section className="model-service-catalog">
              <header>
                <div>
                  <span className="asset-type">模型目录</span>
                  <h3>可用模型</h3>
                  <p>
                    模型 ID 来自当前接入的 /models；仅已启用且验证通过的模型可被使用。
                  </p>
                </div>
                <div className="model-service-catalog-actions">
                  <button
                    className="text-button"
                    onClick={discoverModels}
                    disabled={!selectedConnection || Boolean(busy) || validationActive}
                  >
                    {busy === "model-discover" ? "读取中…" : "同步目录"}
                  </button>
                  <button
                    className="text-button"
                    onClick={openModelCatalog}
                    disabled={!selectedConnection}
                  >
                    管理目录 <ArrowRight size={15} />
                  </button>
                </div>
              </header>
              <div className="model-service-catalog-table" role="table">
                <div className="model-service-catalog-head" role="row">
                  <span>模型 ID</span>
                  <span>推理强度</span>
                  <span>验证状态</span>
                  <span>操作</span>
                </div>
                {selectedConnection ? (
                  visibleCatalogModels.map((model) => (
                    <div
                      className="model-service-catalog-row"
                      role="row"
                      key={model.id}
                    >
                      <strong>{model.model_key}</strong>
                      <span>
                        {model.supported_efforts
                          .map((effort) => EFFORT_LABELS[effort])
                          .join(" · ")}
                      </span>
                      <span
                        className={classNames(
                          "model-validation-badge",
                          model.validation_status,
                        )}
                      >
                        {model.active
                          ? (MODEL_STATUS_LABELS[model.validation_status] ?? "待验证")
                          : "已停用"}
                      </span>
                      {model.active && model.validation_status !== "validated" ? (
                        <button
                          className="text-button"
                          onClick={() => validateCatalogModel(model)}
                          disabled={Boolean(busy) || validationActive}
                        >
                          验证
                        </button>
                      ) : (
                        <button className="text-button" onClick={openModelCatalog}>
                          管理
                        </button>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="model-service-catalog-empty">
                    新增模型服务后，可在这里查看模型可用性。
                  </p>
                )}
                {selectedConnection && visibleCatalogModels.length === 0 && (
                  <p className="model-service-catalog-empty">
                    当前接入未返回可用模型，请同步目录或检查接入权限。
                  </p>
                )}
              </div>
            </section>
          </div>
        ) : (
          <div
            className={classNames(
              "api-layout",
              "model-service-editor",
              `panel-${activePanel}`,
              connections.length > 1 && "has-connections",
            )}
          >
            {connections.length > 1 && (
              <aside className="connection-list">
                <div className="panel-title">
                  <span>接入线路</span>
                  <small>{connections.length} 条</small>
                </div>
                {connections.map((item) => (
                  <button
                    key={item.id}
                    className={selectedConnectionId === item.id ? "active" : ""}
                    onClick={() => setSelectedConnectionId(item.id)}
                  >
                    <div>
                      <b>{item.name}</b>
                      {item.active_version_id && <em>当前默认</em>}
                    </div>
                    <span>{item.provider}</span>
                    <small>
                      <i className={item.active_version ? "online" : ""} />
                      {item.active_version
                        ? `配置 #${item.active_version.version} 已发布`
                        : "尚未发布"}
                    </small>
                  </button>
                ))}
              </aside>
            )}
            <section className="api-editor">
              <header>
                <div>
                  <span className="asset-type">
                    {selectedVersion?.validation_status === "validated"
                      ? "已验证"
                      : selectedVersion?.validation_status === "failed"
                        ? "验证失败"
                        : "配置草稿"}
                  </span>
                  <h2>{selectedConnection?.name ?? "新建模型服务"}</h2>
                  <p>
                    {selectedVersion
                      ? `配置 #${selectedVersion.version} · ${selectedVersion.creator_name} · ${formatTime(selectedVersion.created_at)}`
                      : "创建一条 Responses API 兼容模型服务"}
                  </p>
                  {selectedVersion?.change_note && (
                    <small className="config-change-note">
                      变更原因：{selectedVersion.change_note}
                    </small>
                  )}
                </div>
                {selectedVersion && !editing && activePanel !== "models" && (
                  <button
                    className="secondary-button"
                    disabled={validationActive || Boolean(busy)}
                    onClick={() => {
                      beginConfigEdit(activePanel);
                    }}
                  >
                    <SlidersHorizontal size={17} />
                    创建新版本
                  </button>
                )}
              </header>
              {activePanel === "connection" && (
                <div className="config-section">
                  <CardHeading title="连接信息" note="API 密钥加密保存在服务端" />
                  <div className="config-fields">
                    <label>
                      接入名称
                      <input
                        disabled={!editing}
                        value={form.name}
                        onChange={(event) =>
                          setForm({ ...form, name: event.target.value })
                        }
                      />
                    </label>
                    <label>
                      协议
                      <select
                        disabled={!editing}
                        value={form.provider}
                        onChange={(event) =>
                          setForm({ ...form, provider: event.target.value })
                        }
                      >
                        <option value="responses-compatible">
                          Responses compatible
                        </option>
                      </select>
                    </label>
                    <label>
                      Base URL
                      <input
                        disabled={!editing}
                        value={form.base_url}
                        onChange={(event) =>
                          setForm({ ...form, base_url: event.target.value })
                        }
                        placeholder="https://api.example.com/v1"
                      />
                    </label>
                    <label>
                      API 密钥
                      <input
                        type="password"
                        disabled={!editing}
                        value={form.api_key}
                        onChange={(event) =>
                          setForm({ ...form, api_key: event.target.value })
                        }
                        placeholder={selectedConnection ? "留空则沿用原密钥" : "sk-…"}
                      />
                    </label>
                  </div>
                </div>
              )}
              <ModelCatalogSection
                busy={busy}
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
                selectedConnection={selectedConnection}
                selectedVersion={selectedVersion}
                selectedVersionIsActive={selectedVersionIsActive}
                validationActive={validationActive}
                validationElapsed={validationElapsed}
                validationEvents={validationEvents}
                validationRun={validationRun}
              />
              {!selectedConnection && (
                <div className="config-section" id="model-pipeline">
                  <CardHeading
                    title="连接验证模型"
                    note="新接入需要选择至少一个模型，用于保存与验证连接；任务策略由用户单独维护。"
                  />
                  <div className="model-config-row primary">
                    <span className="model-number">1</span>
                    <div>
                      <b>
                        验证模型 <em>必选</em>
                      </b>
                      <small>用于验证新接入是否可用，不会成为用户的任务策略。</small>
                    </div>
                    <label>
                      模型
                      <select
                        disabled={!editing}
                        required
                        value={form.primary_model ?? ""}
                        onChange={(event) =>
                          selectPipelineModel(
                            "primary_model",
                            "primary_effort",
                            event.target.value,
                          )
                        }
                      >
                        <option value="" disabled>
                          请先添加接入方提供的模型 ID
                        </option>
                        {modelOptions.map((model) => (
                          <option
                            key={model.id}
                            value={model.model_key}
                            disabled={
                              !model.active && form.primary_model !== model.model_key
                            }
                          >
                            {model.display_name === model.model_key
                              ? model.model_key
                              : `${model.display_name} · ${model.model_key}`}
                            {!model.active ? "（已停用）" : ""}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="effort-picker">
                      <span>推理强度</span>
                      <div>
                        {["low", "medium", "high"].map((effort) => (
                          <button
                            type="button"
                            disabled={
                              !editing ||
                              !form.primary_model ||
                              !(
                                modelOptions.find(
                                  (model) => model.model_key === form.primary_model,
                                )?.supported_efforts ?? []
                              ).includes(effort)
                            }
                            className={form.primary_effort === effort ? "active" : ""}
                            key={effort}
                            onClick={() => setForm({ ...form, primary_effort: effort })}
                          >
                            {EFFORT_LABELS[effort]}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}
              <div className="runtime-grid">
                <label>
                  每分钟请求
                  <input
                    type="number"
                    disabled={!editing}
                    value={form.requests_per_minute}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        requests_per_minute: Number(event.target.value),
                      })
                    }
                  />
                </label>
                <label>
                  单任务并发
                  <input
                    type="number"
                    disabled={!editing}
                    value={form.max_workers}
                    onChange={(event) =>
                      setForm({ ...form, max_workers: Number(event.target.value) })
                    }
                  />
                </label>
                <label>
                  请求超时（秒）
                  <input
                    type="number"
                    disabled={!editing}
                    value={form.timeout_seconds}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        timeout_seconds: Number(event.target.value),
                      })
                    }
                  />
                </label>
              </div>
              <div className="config-change-reason">
                <label>
                  配置变更原因
                  <textarea
                    disabled={!editing}
                    value={form.change_note ?? ""}
                    onChange={(event) =>
                      setForm({ ...form, change_note: event.target.value })
                    }
                    rows="3"
                    maxLength="500"
                    placeholder="必填：说明本次新增或调整配置的原因"
                    required
                  />
                </label>
              </div>
              <div className="sticky-config-bar">
                <div>
                  <span
                    className={classNames(
                      "validation-state",
                      selectedVersion?.validation_status,
                    )}
                  >
                    {selectedVersion?.validation_status === "validated" ? (
                      <CheckCircle size={18} />
                    ) : (
                      <WarningCircle size={18} />
                    )}
                    {selectedVersion?.validation_message ||
                      (editing ? "修改会创建新草稿版本" : "配置尚未验证")}
                  </span>
                </div>
                {editing ? (
                  <>
                    <button className="secondary-button" onClick={cancelEdit}>
                      取消
                    </button>
                    <button
                      className="primary-button"
                      onClick={save}
                      disabled={
                        busy === "save" ||
                        !form.change_note?.trim() ||
                        !form.primary_model
                      }
                    >
                      {busy === "save" ? "保存中…" : "保存草稿"}
                    </button>
                  </>
                ) : (
                  selectedVersion && (
                    <>
                      <button
                        className="secondary-button"
                        onClick={validate}
                        disabled={Boolean(busy) || validationActive}
                      >
                        <Power size={17} />
                        {validationActive && validationRun?.kind === "config"
                          ? "验证进行中…"
                          : busy === "validation-start"
                            ? "启动中…"
                            : "验证连接与模型"}
                      </button>
                      <button
                        className="primary-button"
                        disabled={
                          selectedVersion.validation_status !== "validated" ||
                          Boolean(busy) ||
                          validationActive ||
                          selectedVersionIsActive
                        }
                        onClick={publish}
                      >
                        {busy === "publish"
                          ? "发布中…"
                          : selectedVersionIsActive
                            ? "当前已发布"
                            : "发布为当前配置"}
                      </button>
                    </>
                  )
                )}
              </div>
            </section>
            <aside className="config-inspector">
              <section className="content-card">
                <CardHeading title="发布状态" />
                <div
                  className={classNames(
                    "large-connection-status",
                    selectedConnection?.active_version && "online",
                  )}
                >
                  <span />
                  <b>
                    {selectedConnection?.active_version ? "运行配置正常" : "尚未发布"}
                  </b>
                </div>
                <InfoRow
                  label="当前版本"
                  value={
                    selectedConnection?.active_version
                      ? `#${selectedConnection.active_version.version}`
                      : "—"
                  }
                />
                <InfoRow
                  label="连接验证模型"
                  value={selectedConnection?.active_version?.primary_model ?? "—"}
                />
                <InfoRow
                  label="最后验证"
                  value={formatTime(selectedConnection?.active_version?.validated_at)}
                />
              </section>
              {selectedConnection && (
                <section className="content-card config-version-card">
                  <CardHeading
                    title="配置版本"
                    note={`${selectedConnection.versions.length} 个不可变版本`}
                  />
                  <div className="config-version-list">
                    {selectedConnection.versions.map((version) => (
                      <button
                        key={version.id}
                        className={selectedVersion?.id === version.id ? "active" : ""}
                        onClick={() => showVersion(version)}
                      >
                        <b>#{version.version}</b>
                        <span>{version.change_note || "未填写原因"}</span>
                        <em>
                          {version.id === selectedConnection.active_version_id
                            ? "当前运行"
                            : !version.published_at
                              ? "未发布草稿"
                              : "历史版本"}
                        </em>
                        <small>
                          {version.creator_name} · {formatTime(version.created_at)}
                        </small>
                      </button>
                    ))}
                  </div>
                </section>
              )}
              {selectedVersion && (
                <section className="content-card config-diff-card">
                  <CardHeading
                    title="相对上一版"
                    note={
                      previousVersion
                        ? `#${previousVersion.version} → #${selectedVersion.version}`
                        : "首个版本"
                    }
                    action={
                      <button
                        className="secondary-button compact-button"
                        onClick={() => beginConfigEdit("connection", selectedVersion)}
                        disabled={Boolean(busy) || validationActive}
                      >
                        基于此版本创建草稿
                      </button>
                    }
                  />
                  {!previousVersion && (
                    <p className="muted-line">这是该线路的首个配置版本。</p>
                  )}
                  {previousVersion && versionChanges.length === 0 && (
                    <p className="muted-line">模型与运行参数未变化。</p>
                  )}
                  {versionChanges.map(([key, label]) => (
                    <div className="config-diff-row" key={key}>
                      <b>{label}</b>
                      <span>{configValue(key, previousVersion[key])}</span>
                      <ArrowRight size={12} />
                      <span>{configValue(key, selectedVersion[key])}</span>
                    </div>
                  ))}
                </section>
              )}
              <section className="content-card">
                <CardHeading title="配置原则" />
                <p className="inspector-copy">
                  <ShieldCheck size={18} />
                  草稿必须通过真实 API 调用测试，才能发布给新任务使用。
                </p>
                <p className="inspector-copy">
                  <Clock size={18} />
                  新版本不会改变已经启动任务的模型快照。
                </p>
              </section>
            </aside>
          </div>
        )}
      </div>
      {modelEditor && modelDraft && (
        <Modal
          eyebrow="模型列表"
          title={modelEditor === "create" ? "添加模型" : "编辑模型"}
          onClose={closeModelEditor}
        >
          <form
            className="modal-form model-editor-form"
            onSubmit={(event) => {
              event.preventDefault();
              saveModel();
            }}
          >
            <label>
              模型 ID
              <input
                value={modelDraft.model_key}
                disabled={modelEditor === "edit"}
                maxLength="120"
                placeholder="例如 deepseek-reasoner"
                onChange={(event) =>
                  setModelDraft({
                    ...modelDraft,
                    model_key: event.target.value,
                  })
                }
                required
              />
              <small>
                必须与接入方 /models 返回的 ID 完全一致；系统不会预置品牌模型名称。
              </small>
            </label>
            <label>
              显示名称
              <input
                value={modelDraft.display_name}
                maxLength="80"
                placeholder="留空则使用模型 ID"
                onChange={(event) =>
                  setModelDraft({
                    ...modelDraft,
                    display_name: event.target.value,
                  })
                }
              />
            </label>
            <fieldset className="model-effort-selector">
              <legend>支持的推理强度</legend>
              <div>
                {["low", "medium", "high"].map((effort) => {
                  const selected = modelDraft.supported_efforts.includes(effort);
                  return (
                    <button
                      type="button"
                      className={selected ? "active" : ""}
                      key={effort}
                      onClick={() =>
                        setModelDraft({
                          ...modelDraft,
                          supported_efforts: selected
                            ? modelDraft.supported_efforts.filter(
                                (item) => item !== effort,
                              )
                            : [...modelDraft.supported_efforts, effort].sort(
                                (left, right) =>
                                  ["low", "medium", "high"].indexOf(left) -
                                  ["low", "medium", "high"].indexOf(right),
                              ),
                        })
                      }
                    >
                      {EFFORT_LABELS[effort]}
                    </button>
                  );
                })}
              </div>
            </fieldset>
            <p className="form-hint">
              模型验证会使用当前接入最近保存的 Base URL 和 API 密钥发送最小请求。
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={closeModelEditor}
                disabled={busy === "model-save"}
              >
                取消
              </button>
              <button className="primary-button" disabled={busy === "model-save"}>
                {busy === "model-save" ? "保存中…" : "保存模型"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
