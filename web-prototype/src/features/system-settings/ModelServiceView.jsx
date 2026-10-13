import { WarningCircle } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { AntdProvider } from "../../components/AntdProvider";
import {
  EmptyState,
  InlineLoading,
  Modal,
  PageHeading,
} from "../../components/SharedUi";
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
    selectConnection,
    editState,
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
    syncConfirmation,
    cancelDiscoverModels,
    confirmDiscoverModels,
    modelEditState,
  } = catalog;
  const {
    run: validationRun,
    events: validationEvents,
    elapsed: validationElapsed,
    active: validationActive,
    clearRun,
  } = validation;
  const visibleCatalogModels = catalogModels.filter((model) => model.active);
  const validate = () => startValidation(selectedVersion);
  const exitState = modelEditState.pendingExit ? modelEditState : editState;
  return (
    <AntdProvider>
      <div className="standard-page api-page">
        <PageHeading
          title="模型服务"
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
        {loadState === "ready" && loadError && (
          <p role="alert">模型服务更新失败，当前显示上次数据：{loadError}</p>
        )}
        {loadState === "loading" ? (
          <InlineLoading scope="page" label="正在读取模型服务…" />
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
            busy={busy}
            validationActive={validationActive}
            draftVersion={draftVersion}
            discardConfirmation={discardConfirmation}
            visibleCatalogModels={visibleCatalogModels}
            onSelectConnection={selectConnection}
            onStartValidation={startValidation}
            onOpenNewConnection={openNewConnection}
            onEditConnection={() => beginConfigEdit("connection")}
            onEditLimits={() => beginConfigEdit("limits")}
            onOpenVersions={() => setActivePanel("versions")}
            onCancelDiscard={() => setDiscardConfirmation(false)}
            onDiscardDraft={discardDraft}
            onPublishDraft={() => publishVersion(draftVersion)}
            onContinueDraft={() => beginConfigEdit("connection")}
            onValidateDraft={() => startValidation(draftVersion)}
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
            onSelectConnection={selectConnection}
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
            onFieldBlur={editState.touch}
            touchedFields={editState.touched}
            onDiscoverModels={discoverModels}
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
      {!modelEditState.pendingExit && (
        <ModelEditorDialog
          busy={busy}
          editorMode={modelEditor}
          modelDraft={modelDraft}
          onChange={setModelDraft}
          onClose={closeModelEditor}
          onSave={saveModel}
        />
      )}
      {exitState.pendingExit && (
        <Modal title="放弃未保存的修改？" onClose={exitState.continueEditing}>
          <p>尚未保存的内容会丢失。</p>
          <div className="modal-actions">
            <Button onClick={exitState.continueEditing}>继续编辑</Button>
            <Button danger onClick={exitState.discardChanges}>
              放弃修改
            </Button>
          </div>
        </Modal>
      )}
      {syncConfirmation && (
        <Modal title="同步模型目录？" onClose={cancelDiscoverModels}>
          <p>
            将新增或启用接入方返回的模型，并停用未返回的模型。已启动任务仍使用原配置快照。
          </p>
          <div className="modal-actions">
            <Button onClick={cancelDiscoverModels} disabled={Boolean(busy)}>
              取消
            </Button>
            <Button
              type="primary"
              onClick={confirmDiscoverModels}
              disabled={Boolean(busy)}
            >
              {busy === "model-discover" ? "同步中…" : "确认同步"}
            </Button>
          </div>
        </Modal>
      )}
    </AntdProvider>
  );
}
