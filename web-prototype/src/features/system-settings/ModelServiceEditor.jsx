import { classNames } from "../../lib/presentation";
import { ModelCatalogSection } from "./ModelCatalogSection";
import { ModelServiceInspector } from "./ModelServiceInspector";
import { ModelServiceConnectionFields } from "./ModelServiceConnectionFields";
import { ModelServicePipelineFields } from "./ModelServicePipelineFields";
import { ModelServiceRuntimeFields } from "./ModelServiceRuntimeFields";
import { ModelServiceActionBar } from "./ModelServiceActionBar";
import { ModelServiceEditorHeader } from "./ModelServiceEditorHeader";

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
  return (
    <div
      className={classNames(
        "api-layout",
        "model-service-editor",
        `panel-${activePanel}`,
        connections.length > 1 && "has-connections",
        !selectedConnection && "is-new-connection",
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
              disabled={Boolean(busy)}
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
          />
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
          <ModelServicePipelineFields
            form={form}
            onFormChange={onFormChange}
            modelOptions={modelOptions}
            onSelectPipelineModel={onSelectPipelineModel}
            formDisabled={formDisabled}
          />
        )}
        <ModelServiceRuntimeFields
          form={form}
          onFormChange={onFormChange}
          formDisabled={formDisabled}
        />

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
