import { ModelServiceRuntimeSummary } from "./ModelServiceRuntimeSummary";
import { ModelServiceDraftSummary } from "./ModelServiceDraftSummary";
import { ModelServiceCatalogSummary } from "./ModelServiceCatalogSummary";

/** @param {import("./modelServiceViewContracts").ModelServiceSummaryProps} props */
export function ModelServiceSummary({
  connections,
  selectedConnectionId,
  selectedConnection,
  activeVersion,
  availableModelCount,
  busy,
  validationActive,
  draftVersion,
  discardConfirmation,
  visibleCatalogModels,
  onSelectConnection,
  onStartValidation,
  onOpenNewConnection,
  onEditConnection,
  onEditLimits,
  onOpenVersions,
  onCancelDiscard,
  onDiscardDraft,
  onPublishDraft,
  onContinueDraft,
  onConfirmDiscard,
  onDiscoverModels,
  onOpenModelCatalog,
  onValidateCatalogModel,
}) {
  return (
    <div className="model-service-summary">
      {connections.length > 1 && (
        <label className="model-service-selector">
          模型服务
          <select
            value={selectedConnectionId ?? ""}
            onChange={(event) => onSelectConnection(event.target.value)}
            disabled={Boolean(busy)}
          >
            {connections.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <ModelServiceRuntimeSummary
        selectedConnection={selectedConnection}
        activeVersion={activeVersion}
        availableModelCount={availableModelCount}
        busy={busy}
        validationActive={validationActive}
        onStartValidation={onStartValidation}
        onOpenNewConnection={onOpenNewConnection}
        onEditConnection={onEditConnection}
        onEditLimits={onEditLimits}
        onOpenVersions={onOpenVersions}
      />
      {draftVersion && (
        <ModelServiceDraftSummary
          draftVersion={draftVersion}
          activeVersion={activeVersion}
          busy={busy}
          validationActive={validationActive}
          discardConfirmation={discardConfirmation}
          onCancelDiscard={onCancelDiscard}
          onDiscardDraft={onDiscardDraft}
          onPublishDraft={onPublishDraft}
          onContinueDraft={onContinueDraft}
          onConfirmDiscard={onConfirmDiscard}
        />
      )}
      <ModelServiceCatalogSummary
        selectedConnection={selectedConnection}
        visibleCatalogModels={visibleCatalogModels}
        busy={busy}
        validationActive={validationActive}
        onDiscoverModels={onDiscoverModels}
        onOpenModelCatalog={onOpenModelCatalog}
        onValidateCatalogModel={onValidateCatalogModel}
      />
    </div>
  );
}
