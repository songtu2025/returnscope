import { CardHeading } from "../../components/SharedUi";
import { EFFORT_LABELS } from "../../constants";

/** @param {Pick<import("./modelServiceViewContracts").ModelServiceEditorProps, "form" | "onFormChange" | "modelOptions" | "onSelectPipelineModel"> & {formDisabled: boolean}} props */
export function ModelServicePipelineFields({
  form,
  onFormChange,
  modelOptions,
  onSelectPipelineModel,
  formDisabled,
}) {
  return (
    <div className="config-section" id="model-pipeline">
      <CardHeading
        title="共享验证模型"
        note="用于验证连接及分类标准的 Review 样本；保存、验证并发布配置后生效。"
      />
      <div className="model-config-row primary">
        <span className="model-number">1</span>
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
          {!form.primary_model && (
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
