import { Plus } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { useState } from "react";
import { CardHeading } from "../../components/SharedUi";
import { ModelCatalogRow } from "./ModelCatalogRow";
import { ValidationProcess } from "./ModelValidationProcess";

/** @typedef {import("../../shared/api/systemSettingsContracts").CatalogModel} CatalogModel */
/** @typedef {import("../../shared/api/systemSettingsContracts").ConfigVersion} ConfigVersion */
/** @typedef {import("../../shared/api/systemSettingsContracts").ModelConnection} ModelConnection */
/** @typedef {import("../../shared/api/systemSettingsContracts").ValidationRun} ValidationRun */
/** @typedef {import("../../shared/api/systemSettingsContracts").ValidationEvent} ValidationEvent */

/**
 * @param {{
 *   busy: string,
 *   catalogModels: CatalogModel[],
 *   focusModelId: string | null,
 *   focusedModelRef: import("react").Ref<HTMLDivElement>,
 *   onCloseValidation: () => void,
 *   onOpenModelEditor: (model?: CatalogModel) => void,
 *   onDiscoverModels: () => void,
 *   onToggleModel: (model: CatalogModel) => void,
 *   onValidateModel: (model: CatalogModel) => void,
 *   selectedConnection: ModelConnection | null | undefined,
 *   selectedVersion: ConfigVersion | null,
 *   validationActive: boolean,
 *   validationElapsed: number,
 *   validationEvents: ValidationEvent[],
 *   validationRun: ValidationRun | null,
 * }} props
 */
export function ModelCatalogSection(props) {
  const [showInactive, setShowInactive] = useState(Boolean(props.focusModelId));
  const visibleModels = props.catalogModels.filter(
    (model) => model.active || showInactive,
  );
  return (
    <div className="config-section" id="available-models">
      <ModelCatalogHeading
        busy={props.busy}
        selectedConnection={props.selectedConnection}
        onOpenModelEditor={props.onOpenModelEditor}
        onDiscoverModels={props.onDiscoverModels}
      />
      <label className="model-catalog-filter">
        <input
          type="checkbox"
          checked={showInactive}
          onChange={(event) => setShowInactive(event.target.checked)}
        />
        显示停用模型
      </label>
      <div className="model-catalog-list">
        {!visibleModels.length && (
          <p className="muted-line">暂无模型，请同步目录或添加模型。</p>
        )}
        {visibleModels.map((model) => (
          <ModelCatalogRow
            key={model.id}
            model={model}
            busy={props.busy}
            focusModelId={props.focusModelId}
            focusedModelRef={props.focusedModelRef}
            onOpenModelEditor={props.onOpenModelEditor}
            onToggleModel={props.onToggleModel}
            onValidateModel={props.onValidateModel}
            selectedConnection={props.selectedConnection}
            validationActive={props.validationActive}
            validationRun={props.validationRun}
          />
        ))}
      </div>
      <ValidationProcess
        busy={props.busy}
        onClose={props.onCloseValidation}
        selectedVersion={props.selectedVersion}
        validationActive={props.validationActive}
        validationElapsed={props.validationElapsed}
        validationEvents={props.validationEvents}
        validationRun={
          props.validationRun?.kind === "model" ? props.validationRun : null
        }
      />
    </div>
  );
}

/** @param {Pick<Parameters<typeof ModelCatalogSection>[0], "busy" | "selectedConnection" | "onOpenModelEditor" | "onDiscoverModels">} props */
function ModelCatalogHeading({
  busy,
  selectedConnection,
  onOpenModelEditor,
  onDiscoverModels,
}) {
  return (
    <CardHeading
      title="模型目录"
      note={
        selectedConnection
          ? "已启用且验证通过的模型可用于分析任务。"
          : "请添加接入方提供的模型 ID；保存后可同步真实目录并验证。"
      }
      action={
        <div className="model-service-catalog-actions">
          {selectedConnection && (
            <Button onClick={onDiscoverModels} disabled={Boolean(busy)}>
              同步模型目录
            </Button>
          )}
          <Button
            autoInsertSpace={false}
            icon={<Plus size={16} />}
            onClick={() => onOpenModelEditor()}
            disabled={Boolean(busy)}
          >
            添加模型
          </Button>
        </div>
      }
    />
  );
}
