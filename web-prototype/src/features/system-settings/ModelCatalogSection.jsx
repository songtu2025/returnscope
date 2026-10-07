import { Plus } from "@phosphor-icons/react";
import Button from "antd/es/button";
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
 *   onPublish: () => void,
 *   onToggleModel: (model: CatalogModel) => void,
 *   onValidateModel: (model: CatalogModel) => void,
 *   selectedConnection: ModelConnection | null | undefined,
 *   selectedVersion: ConfigVersion | null,
 *   selectedVersionIsActive: boolean,
 *   validationActive: boolean,
 *   validationElapsed: number,
 *   validationEvents: ValidationEvent[],
 *   validationRun: ValidationRun | null,
 * }} props
 */
export function ModelCatalogSection(props) {
  return (
    <div className="config-section" id="available-models">
      <ModelCatalogHeading
        busy={props.busy}
        selectedConnection={props.selectedConnection}
        onOpenModelEditor={props.onOpenModelEditor}
      />
      <div className="model-catalog-list">
        {props.catalogModels.map((model) => (
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
        onPublish={props.onPublish}
        selectedVersion={props.selectedVersion}
        selectedVersionIsActive={props.selectedVersionIsActive}
        validationActive={props.validationActive}
        validationElapsed={props.validationElapsed}
        validationEvents={props.validationEvents}
        validationRun={props.validationRun}
      />
    </div>
  );
}

/** @param {Pick<Parameters<typeof ModelCatalogSection>[0], "busy" | "selectedConnection" | "onOpenModelEditor">} props */
function ModelCatalogHeading({ busy, selectedConnection, onOpenModelEditor }) {
  return (
    <CardHeading
      title="可用模型"
      note={
        selectedConnection
          ? "目录来自当前接入的 /models；仅已启用且验证通过的模型可供选择。"
          : "请添加接入方提供的模型 ID；保存后可同步真实目录并验证。"
      }
      action={
        <Button
          autoInsertSpace={false}
          icon={<Plus size={16} />}
          onClick={() => onOpenModelEditor()}
          disabled={Boolean(busy)}
        >
          添加模型
        </Button>
      }
    />
  );
}
