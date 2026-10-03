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
 * @typedef {{
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
 *   nameError: string,
 *   baseUrlError: string,
 *   apiKeyError: string,
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
 * }} ModelServiceEditorProps
 */

/**
 * @typedef {{
 *   connections: ModelConnection[],
 *   selectedConnectionId: string | null,
 *   selectedConnection: ModelConnection | null | undefined,
 *   activeVersion: ConfigVersion | null,
 *   availableModelCount: number,
 *   busy: string,
 *   validationActive: boolean,
 *   draftVersion: ConfigVersion | null | undefined,
 *   discardConfirmation: boolean,
 *   visibleCatalogModels: CatalogModel[],
 *   onSelectConnection: (id: string) => void,
 *   onStartValidation: (version: ConfigVersion) => void,
 *   onOpenNewConnection: () => void,
 *   onEditConnection: () => void,
 *   onEditLimits: () => void,
 *   onOpenVersions: () => void,
 *   onCancelDiscard: () => void,
 *   onDiscardDraft: () => void,
 *   onPublishDraft: () => void,
 *   onContinueDraft: () => void,
 *   onConfirmDiscard: () => void,
 *   onDiscoverModels: () => void,
 *   onOpenModelCatalog: () => void,
 *   onValidateCatalogModel: (model: CatalogModel) => void,
 * }} ModelServiceSummaryProps
 */

export {};
