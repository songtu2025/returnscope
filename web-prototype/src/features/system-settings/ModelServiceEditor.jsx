import {
  CheckCircle,
  Power,
  SlidersHorizontal,
  WarningCircle,
} from "@phosphor-icons/react";
import Button from "antd/es/button";
import Input from "antd/es/input";
import { CardHeading } from "../../components/SharedUi";
import { EFFORT_LABELS } from "../../constants";
import { classNames, formatTime } from "../../lib/presentation";
import { ModelCatalogSection } from "./ModelCatalogSection";
import { ModelServiceInspector } from "./ModelServiceInspector";

/** @typedef {import("../../shared/api/systemSettingsContracts").ActivePanel} ActivePanel */
/** @typedef {import("../../shared/api/systemSettingsContracts").CatalogModel} CatalogModel */
/** @typedef {import("../../shared/api/systemSettingsContracts").ConfigVersion} ConfigVersion */
/** @typedef {import("../../shared/api/systemSettingsContracts").ModelConnection} ModelConnection */
/** @typedef {import("../../shared/api/systemSettingsContracts").ModelOption} ModelOption */
/** @typedef {import("../../shared/api/systemSettingsContracts").ModelServiceForm} ModelServiceForm */
/** @typedef {import("../../shared/api/systemSettingsContracts").PipelineModelKey} PipelineModelKey */
/** @typedef {import("../../shared/api/systemSettingsContracts").PipelineEffortKey} PipelineEffortKey */
/** @typedef {import("../../shared/api/systemSettingsContracts").ValidationRun} ValidationRun */
/** @typedef {import("../../shared/api/systemSettingsContracts").ValidationEvent} ValidationEvent */
/** @typedef {import("../../shared/api/systemSettingsContracts").VersionChanges} VersionChanges */

/**
 * @param {{
 *   activePanel: ActivePanel,
 *   connections: ModelConnection[],
 *   selectedConnectionId: string | null,
 *   onSelectConnection: (id: string) => void,
 *   selectedVersion: ConfigVersion | null,
 *   selectedConnection: ModelConnection | null | undefined,
 *   editing: boolean,
 *   validationActive: boolean,
 *   busy: string,
 *   onBeginEdit: (panel: ActivePanel) => void,
 *   form: ModelServiceForm,
 *   onFormChange: (form: ModelServiceForm) => void,
 *   baseUrlError: string,
 *   catalogModels: CatalogModel[],
 *   focusModelId: string | null,
 *   focusedModelRef: import("react").Ref<HTMLDivElement>,
 *   onCloseValidation: () => void,
 *   onOpenModelEditor: (model?: CatalogModel) => void,
 *   onPublish: () => void,
 *   onToggleModel: (model: CatalogModel) => void,
 *   onValidateModel: (model: CatalogModel) => void,
 *   selectedVersionIsActive: boolean,
 *   validationElapsed: number,
 *   validationEvents: ValidationEvent[],
 *   validationRun: ValidationRun | null,
 *   modelOptions: ModelOption[],
 *   onSelectPipelineModel: (modelKey: PipelineModelKey, effortKey: PipelineEffortKey, value: string) => void,
 *   configFormErrors: string[],
 *   onCancelEdit: () => void,
 *   onSave: () => void,
 *   saveDisabled: boolean,
 *   onValidate: () => void,
 *   previousVersion: ConfigVersion | null | undefined,
 *   versionChanges: VersionChanges,
 *   onShowVersion: (version: ConfigVersion) => void,
 *   onCreateDraft: (version: ConfigVersion) => void,
 * }} props
 */
export function ModelServiceEditor({
  activePanel,
  connections,
  selectedConnectionId,
  onSelectConnection,
  selectedVersion,
  selectedConnection,
  editing,
  validationActive,
  busy,
  onBeginEdit,
  form,
  onFormChange,
  baseUrlError,
  catalogModels,
  focusModelId,
  focusedModelRef,
  onCloseValidation,
  onOpenModelEditor,
  onPublish,
  onToggleModel,
  onValidateModel,
  selectedVersionIsActive,
  validationElapsed,
  validationEvents,
  validationRun,
  modelOptions,
  onSelectPipelineModel,
  configFormErrors,
  onCancelEdit,
  onSave,
  saveDisabled,
  onValidate,
  previousVersion,
  versionChanges,
  onShowVersion,
  onCreateDraft,
}) {
  return (
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
              onClick={() => onSelectConnection(item.id)}
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
            <Button
              autoInsertSpace={false}
              icon={<SlidersHorizontal size={17} />}
              disabled={validationActive || Boolean(busy)}
              onClick={() => {
                onBeginEdit(activePanel);
              }}
            >
              创建新版本
            </Button>
          )}
        </header>
        {activePanel === "connection" && (
          <div className="config-section">
            <CardHeading title="连接信息" note="API 密钥加密保存在服务端" />
            <div className="config-fields">
              <label>
                接入名称
                <Input
                  disabled={!editing}
                  value={form.name}
                  onChange={(event) =>
                    onFormChange({ ...form, name: event.target.value })
                  }
                />
              </label>
              <label>
                协议
                <select
                  disabled={!editing}
                  value={form.provider}
                  onChange={(event) =>
                    onFormChange({ ...form, provider: event.target.value })
                  }
                >
                  <option value="responses-compatible">Responses compatible</option>
                </select>
              </label>
              <label>
                Base URL
                <input
                  disabled={!editing}
                  aria-label="Base URL"
                  value={form.base_url}
                  onChange={(event) =>
                    onFormChange({ ...form, base_url: event.target.value })
                  }
                  placeholder="https://api.example.com/v1"
                  aria-invalid={Boolean(baseUrlError)}
                  aria-describedby={
                    baseUrlError ? "model-service-base-url-error" : undefined
                  }
                />
                {baseUrlError && (
                  <small
                    id="model-service-base-url-error"
                    className="config-field-error"
                    role="alert"
                  >
                    {baseUrlError}
                  </small>
                )}
              </label>
              <label>
                API 密钥
                <input
                  type="password"
                  disabled={!editing}
                  value={form.api_key}
                  onChange={(event) =>
                    onFormChange({ ...form, api_key: event.target.value })
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
          onCloseValidation={onCloseValidation}
          onOpenModelEditor={onOpenModelEditor}
          onPublish={onPublish}
          onToggleModel={onToggleModel}
          onValidateModel={onValidateModel}
          selectedConnection={selectedConnection}
          selectedVersion={selectedVersion}
          selectedVersionIsActive={selectedVersionIsActive}
          validationActive={validationActive}
          validationElapsed={validationElapsed}
          validationEvents={validationEvents}
          validationRun={validationRun}
        />
        {activePanel === "connection" && (
          <div className="config-section" id="model-pipeline">
            <CardHeading
              title="共享验证模型"
              note="用于验证连接及分类标准的 Review 样本；保存、验证并发布配置后生效。"
            />
            <div className="model-config-row primary">
              <span className="model-number">1</span>
              <div>
                <b>
                  验证模型 <em>必选</em>
                </b>
                <small>个人模型偏好与任务策略独立维护，不会随此选择更改。</small>
              </div>
              <label>
                模型
                <select
                  disabled={!editing}
                  aria-label="模型"
                  required
                  value={form.primary_model ?? ""}
                  onChange={(event) =>
                    onSelectPipelineModel(
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
                      disabled={!model.active && form.primary_model !== model.model_key}
                    >
                      {model.display_name === model.model_key
                        ? model.model_key
                        : `${model.display_name} · ${model.model_key}`}
                      {!model.active ? "（已停用）" : ""}
                    </option>
                  ))}
                </select>
                {!form.primary_model && (
                  <small className="config-field-error">请选择验证模型。</small>
                )}
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
                      onClick={() => onFormChange({ ...form, primary_effort: effort })}
                    >
                      {/** @type {Record<string, string>} */ (EFFORT_LABELS)[effort]}
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
                onFormChange({
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
                onFormChange({
                  ...form,
                  max_workers: Number(event.target.value),
                })
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
                onFormChange({
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
              aria-label="配置变更原因"
              value={form.change_note ?? ""}
              onChange={(event) =>
                onFormChange({ ...form, change_note: event.target.value })
              }
              rows={3}
              maxLength={500}
              placeholder="必填：说明本次新增或调整配置的原因"
              required
            />
            {!form.change_note?.trim() && (
              <small className="config-field-error">请填写配置变更原因。</small>
            )}
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
            {configFormErrors.length > 0 && (
              <small className="config-save-disabled-reason" role="status">
                暂时无法保存：{configFormErrors.join("；")}
              </small>
            )}
          </div>
          {editing ? (
            <>
              <Button autoInsertSpace={false} onClick={onCancelEdit}>
                取消
              </Button>
              <button
                className="primary-button"
                onClick={onSave}
                disabled={saveDisabled}
              >
                {busy === "save" ? "保存中…" : "保存草稿"}
              </button>
            </>
          ) : (
            selectedVersion && (
              <>
                <button
                  className="secondary-button"
                  onClick={onValidate}
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
                  onClick={onPublish}
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
      <ModelServiceInspector
        selectedConnection={selectedConnection}
        selectedVersion={selectedVersion}
        previousVersion={previousVersion}
        versionChanges={versionChanges}
        busy={busy}
        validationActive={validationActive}
        onShowVersion={onShowVersion}
        onCreateDraft={onCreateDraft}
      />
    </div>
  );
}
