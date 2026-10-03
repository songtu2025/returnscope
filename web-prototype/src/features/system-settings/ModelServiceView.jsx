import { WarningCircle } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { AntdProvider } from "../../components/AntdProvider";
import { EmptyState, InlineLoading, PageHeading } from "../../components/SharedUi";
import { ModelEditorDialog } from "./ModelEditorDialog";
import { ModelServiceEditor } from "./ModelServiceEditor";
import { ModelServiceSummary } from "./ModelServiceSummary";
import { errorMessage } from "./modelServiceConfig";

/**
 * @param {object} props
 * @param {ReturnType<typeof import("./useModelServiceConnections").useModelServiceConnections>} props.connectionState
 * @param {ReturnType<typeof import("./useModelServiceConfiguration").useModelServiceConfiguration>} props.configuration
 * @param {ReturnType<typeof import("./useModelServiceCatalog").useModelServiceCatalog>} props.catalog
 * @param {ReturnType<typeof import("./useModelValidationRun").useModelValidationRun>} props.validation
 * @param {(version?: import("../../shared/api/systemSettingsContracts").ConfigVersion | null) => Promise<void>} props.startValidation
 * @param {string} props.busy
 * @param {string | null} props.focusModelId
 * @param {import("react").RefObject<HTMLDivElement | null>} props.focusedModelRef
 * @param {(message: string, type?: "success" | "error") => void} props.notify
 */
export function ModelServiceView({
  connectionState,
  configuration,
  catalog,
  validation,
  startValidation,
  busy,
  focusModelId,
  focusedModelRef,
  notify,
}) {
  const {
    connections,
    selectedConnectionId,
    setSelectedConnectionId,
    selectedConnection,
    activeVersion,
    draftVersion,
    load,
    loadState,
    loadError,
  } = connectionState;
  const {
    form,
    setForm,
    editing,
    activePanel,
    setActivePanel,
    selectedVersion,
    discardConfirmation,
    setDiscardConfirmation,
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
    showVersion,
  } = configuration;
  const {
    catalogModels,
    modelEditor,
    modelDraft,
    setModelDraft,
    openModelEditor,
    closeModelEditor,
    saveModel,
    toggleModel,
    validateCatalogModel,
    discoverModels,
  } = catalog;
  const {
    run: validationRun,
    events: validationEvents,
    elapsed: validationElapsed,
    active: validationActive,
    clearRun,
  } = validation;
  const visibleCatalogModels = catalogModels.filter((model) => model.active);
  const availableModelCount = catalogModels.filter(
    (model) => model.active && model.validation_status === "validated",
  ).length;
  const validate = () => startValidation(selectedVersion);
  return (
    <AntdProvider>
      <div className="standard-page api-page">
        <PageHeading
          eyebrow="共享系统配置"
          title="模型服务"
          description="维护共享接入、模型可用性与运行限制；个人策略与任务选择在各自页面保存。"
          action={
            activePanel ? (
              <Button
                autoInsertSpace={false}
                onClick={closePanel}
                disabled={Boolean(busy)}
              >
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
            onCloseValidation={clearRun}
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
