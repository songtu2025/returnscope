import { classNames } from "../../lib/presentation";
import { ModelCatalogSection } from "./ModelCatalogSection";
import { ModelServiceInspector } from "./ModelServiceInspector";
import { ModelServiceConnectionFields } from "./ModelServiceConnectionFields";
import { ModelServicePipelineFields } from "./ModelServicePipelineFields";
import { ModelServiceRuntimeFields } from "./ModelServiceRuntimeFields";
import { ModelServiceActionBar } from "./ModelServiceActionBar";
import { ModelServiceEditorHeader } from "./ModelServiceEditorHeader";
import { ValidationProcess } from "./ModelValidationProcess";
import { configValue } from "./modelServiceConfig";

/** @param {import("./modelServiceViewContracts").ModelServiceEditorProps} props */
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
  nameError,
  baseUrlError,
  apiKeyError,
  touchedFields,
  onFieldBlur,
  onDiscoverModels,
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
  const formDisabled = !editing || Boolean(busy);
  const validationVersion =
    selectedConnection?.versions.find(
      (version) => version.id === validationRun?.config_version_id,
    ) ??
    (validationRun?.kind === "config" && validationRun.target_id === selectedVersion?.id
      ? selectedVersion
      : null);
  return (
    <div
      className={classNames(
        "api-layout",
        "model-service-editor",
        `panel-${activePanel}`,
        connections.length > 1 && "has-connections",
      )}
    >
      {connections.length > 1 && activePanel !== "versions" && (
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
              disabled={Boolean(busy)}
            >
              <div>
                <b>{item.name}</b>
                {item.active_version_id && <em>已发布</em>}
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
      {activePanel !== "versions" && (
        <section className="api-editor">
          <ModelServiceEditorHeader
            selectedVersion={selectedVersion}
            selectedConnection={selectedConnection}
            editing={editing}
            activePanel={activePanel}
            validationActive={validationActive}
            busy={busy}
            onBeginEdit={onBeginEdit}
          />
          {activePanel === "connection" && (
            <ModelServiceConnectionFields
              form={form}
              onFormChange={onFormChange}
              selectedConnection={selectedConnection}
              nameError={nameError}
              baseUrlError={baseUrlError}
              apiKeyError={apiKeyError}
              formDisabled={formDisabled}
              onFieldBlur={onFieldBlur}
            />
          )}
          {(activePanel === "models" ||
            (activePanel === "connection" && !selectedConnection)) && (
            <ModelCatalogSection
              busy={busy}
              catalogModels={catalogModels}
              focusModelId={focusModelId}
              focusedModelRef={focusedModelRef}
              onCloseValidation={onCloseValidation}
              onOpenModelEditor={onOpenModelEditor}
              onToggleModel={onToggleModel}
              onValidateModel={onValidateModel}
              selectedConnection={selectedConnection}
              selectedVersion={validationVersion}
              onDiscoverModels={onDiscoverModels}
              validationActive={validationActive}
              validationElapsed={validationElapsed}
              validationEvents={validationEvents}
              validationRun={validationRun}
            />
          )}
          {activePanel === "connection" && (
            <ModelServicePipelineFields
              form={form}
              onFormChange={onFormChange}
              modelOptions={modelOptions}
              onSelectPipelineModel={onSelectPipelineModel}
              formDisabled={formDisabled}
              onFieldBlur={onFieldBlur}
              touchedFields={touchedFields}
            />
          )}
          {activePanel === "limits" && (
            <ModelServiceRuntimeFields
              form={form}
              onFormChange={onFormChange}
              formDisabled={formDisabled}
              onFieldBlur={onFieldBlur}
              touchedFields={touchedFields}
              configFormErrors={configFormErrors}
            />
          )}
          {activePanel === "validation" && (
            <>
              <div className="model-service-validation-scope">
                <h3>验证连接与选定模型</h3>
                <p>
                  配置 #{selectedVersion?.version} · {selectedVersion?.primary_model} ·{" "}
                  {configValue("primary_effort", selectedVersion?.primary_effort)}
                </p>
                <p>
                  发送一次最小请求，检查地址、密钥、模型和推理强度。其他模型可在模型目录中单独验证。
                </p>
              </div>
              <ValidationProcess
                busy={busy}
                onClose={onCloseValidation}
                selectedVersion={validationVersion}
                validationActive={validationActive}
                validationElapsed={validationElapsed}
                validationEvents={validationEvents}
                validationRun={
                  validationRun?.kind === "config" &&
                  validationRun.target_id === selectedVersion?.id
                    ? validationRun
                    : null
                }
              />
            </>
          )}

          {activePanel !== "models" && (
            <ModelServiceActionBar
              selectedVersion={selectedVersion}
              editing={editing}
              busy={busy}
              validationActive={validationActive}
              validationRun={validationRun}
              configFormErrors={configFormErrors}
              onCancelEdit={onCancelEdit}
              onSave={onSave}
              saveDisabled={saveDisabled}
              onValidate={onValidate}
              onPublish={onPublish}
              selectedVersionIsActive={selectedVersionIsActive}
            />
          )}
        </section>
      )}
      {activePanel === "versions" && (
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
      )}
    </div>
  );
}
