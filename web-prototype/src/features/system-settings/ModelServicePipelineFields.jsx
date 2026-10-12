import { CardHeading } from "../../components/SharedUi";
import { EFFORT_LABELS } from "../../constants";

/** @param {Pick<import("./modelServiceViewContracts").ModelServiceEditorProps, "form" | "onFormChange" | "modelOptions" | "onSelectPipelineModel" | "onFieldBlur" | "touchedFields"> & {formDisabled: boolean}} props */
export function ModelServicePipelineFields({
  form,
  onFormChange,
  modelOptions,
  onSelectPipelineModel,
  formDisabled,
  onFieldBlur,
  touchedFields,
}) {
  return (
    <div className="config-section" id="model-pipeline">
      <CardHeading
        title="验证模型"
        note="服务验证仅发送一次最小请求；分类标准样本也使用此模型。"
      />
      <div className="model-config-row primary">
        <div>
          <b>
            验证模型 <em>必选</em>
          </b>
          <small>个人模型偏好与任务策略独立维护，不会随此选择更改。</small>
        </div>
        <label>
          模型
          <select
            disabled={formDisabled}
            aria-label="模型"
            required
            onBlur={() => onFieldBlur("primary_model")}
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
          {touchedFields.includes("primary_model") && !form.primary_model && (
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
                  formDisabled ||
                  !form.primary_model ||
                  !(
                    modelOptions.find((model) => model.model_key === form.primary_model)
                      ?.supported_efforts ?? []
                  ).includes(effort)
                }
                className={form.primary_effort === effort ? "active" : ""}
                aria-pressed={form.primary_effort === effort}
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
  );
}
