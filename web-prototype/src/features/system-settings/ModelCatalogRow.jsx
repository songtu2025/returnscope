import { EFFORT_LABELS, MODEL_STATUS_LABELS } from "../../constants";
import { classNames, formatTime } from "../../lib/presentation";

/** @typedef {import("./modelServiceViewContracts").ModelServiceEditorProps} EditorProps */
/** @typedef {import("../../shared/api/systemSettingsContracts").CatalogModel} CatalogModel */
/** @typedef {Pick<EditorProps, "busy" | "focusModelId" | "focusedModelRef" | "onOpenModelEditor" | "onToggleModel" | "onValidateModel" | "selectedConnection" | "validationActive" | "validationRun"> & {model: CatalogModel}} CatalogRowProps */
const EFFORT_LABEL_MAP = /** @type {Record<string, string>} */ (EFFORT_LABELS);
const MODEL_STATUS_LABEL_MAP = /** @type {Record<string, string>} */ (
  MODEL_STATUS_LABELS
);

/** @param {CatalogRowProps} props */
export function ModelCatalogRow(props) {
  const { model, focusModelId, focusedModelRef } = props;
  return (
    <div
      ref={String(model.id) === String(focusModelId) ? focusedModelRef : null}
      className={classNames(
        "model-catalog-row",
        !model.active && "inactive",
        String(model.id) === String(focusModelId) && "is-targeted",
      )}
    >
      <div className="model-catalog-name">
        <b>{model.display_name}</b>
        <code>{model.model_key}</code>
        {model.updater_name && (
          <small>
            最近修改：{model.updater_name} · {formatTime(model.updated_at)}
          </small>
        )}
      </div>
      <div className="model-effort-tags">
        {model.supported_efforts.map((effort) => (
          <span key={effort}>{EFFORT_LABEL_MAP[effort]}</span>
        ))}
      </div>
      <span
        className={classNames("model-validation-badge", model.validation_status)}
        title={model.validation_message || ""}
      >
        {model.active
          ? (MODEL_STATUS_LABEL_MAP[model.validation_status] ?? "待验证")
          : "已停用"}
      </span>
      <ModelCatalogActions
        model={model}
        busy={props.busy}
        selectedConnection={props.selectedConnection}
        validationActive={props.validationActive}
        validationRun={props.validationRun}
        onValidateModel={props.onValidateModel}
        onOpenModelEditor={props.onOpenModelEditor}
        onToggleModel={props.onToggleModel}
      />
    </div>
  );
}

/** @param {Omit<CatalogRowProps, "focusModelId" | "focusedModelRef">} props */
function ModelCatalogActions({
  model,
  busy,
  onOpenModelEditor,
  onToggleModel,
  onValidateModel,
  selectedConnection,
  validationActive,
  validationRun,
}) {
  return (
    <div className="model-catalog-actions">
      {selectedConnection && model.active && (
        <button
          type="button"
          onClick={() => onValidateModel(model)}
          disabled={Boolean(busy) || validationActive}
        >
          {validationActive && validationRun?.target_id === model.id
            ? "验证中…"
            : busy === "validation-start"
              ? "启动中…"
              : "验证"}
        </button>
      )}
      <button
        type="button"
        onClick={() => onOpenModelEditor(model)}
        disabled={Boolean(busy) || validationActive}
      >
        编辑
      </button>
      <button
        type="button"
        onClick={() => onToggleModel(model)}
        disabled={Boolean(busy) || validationActive}
      >
        {model.active ? "停用" : "启用"}
      </button>
    </div>
  );
}
