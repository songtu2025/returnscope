import { CaretDown } from "@phosphor-icons/react";
import { EFFORT_LABELS } from "../../constants";

const MODEL_STAGES = [
  ["低成本初筛", "cheap_model", "cheap_effort", false],
  ["主分析", "primary_model", "primary_effort", true],
  ["风险复核", "secondary_model", "secondary_effort", false],
];

export function TaskConfigurationStep({
  headingRef,
  form,
  onFormChange,
  publishedConfigs,
  selectedConfig,
  availableModels,
  modelPolicy,
  onConnectionChange,
  onModelPolicyChange,
  children,
}) {
  return (
    <section
      className="task-config-panel task-launch-panel"
      aria-labelledby="task-launch-title"
    >
      <div className="task-config-section">
        <header className="task-launch-heading">
          <h2 id="task-launch-title" ref={headingRef} tabIndex={-1}>
            确认并开始分析
          </h2>
          <p>为任务命名，确认本次使用的分析模型。</p>
        </header>
        <label className="task-config-choice task-title-input">
          任务名称
          <input
            value={form.title}
            maxLength="120"
            placeholder="为本次分析起个名字"
            onChange={(event) => onFormChange({ ...form, title: event.target.value })}
          />
        </label>
        <details className="task-advanced-settings task-model-settings">
          <summary aria-label="分析设置">
            <div className="task-model-selection">
              <span>主分析模型</span>
              <strong>
                {availableModels.find(
                  (model) => model.model_key === modelPolicy.primary_model,
                )?.display_name ||
                  modelPolicy.primary_model ||
                  "默认模型"}
              </strong>
              <small>
                {selectedConfig?.connection_name} · 推理强度
                {EFFORT_LABELS[modelPolicy.primary_effort] ??
                  modelPolicy.primary_effort}
              </small>
              {MODEL_STAGES.filter(
                ([, modelKey, , required]) => !required && modelPolicy[modelKey],
              ).map(([label, modelKey, effortKey]) => (
                <small key={modelKey}>
                  {label}：
                  {availableModels.find(
                    (model) => model.model_key === modelPolicy[modelKey],
                  )?.display_name || modelPolicy[modelKey]}
                  {" · 推理强度"}
                  {EFFORT_LABELS[modelPolicy[effortKey]] ?? modelPolicy[effortKey]}
                </small>
              ))}
            </div>
            <span className="task-model-edit">
              更改设置 <CaretDown size={16} />
            </span>
          </summary>
          <div className="task-advanced-body">
            <label className="task-config-choice">
              模型接入
              <select
                value={form.config_version_id}
                onChange={(event) => onConnectionChange(event.target.value)}
              >
                {publishedConfigs.map((config) => (
                  <option key={config.id} value={config.id}>
                    {config.connection_name} · 配置 #{config.version}
                  </option>
                ))}
              </select>
              <small>使用已验证的接入，以下设置仅用于本次任务。</small>
            </label>
            <div className="task-model-policy-grid">
              {MODEL_STAGES.map(([label, modelKey, effortKey, required]) => {
                const selectedModel = availableModels.find(
                  (item) => item.model_key === modelPolicy[modelKey],
                );
                return (
                  <label className="task-config-choice" key={modelKey}>
                    {label}
                    <select
                      value={modelPolicy[modelKey] || ""}
                      onChange={(event) => {
                        const model = availableModels.find(
                          (item) => item.model_key === event.target.value,
                        );
                        onModelPolicyChange({
                          [modelKey]: event.target.value,
                          [effortKey]: model?.supported_efforts.includes(
                            modelPolicy[effortKey],
                          )
                            ? modelPolicy[effortKey]
                            : (model?.supported_efforts[0] ?? "medium"),
                        });
                      }}
                    >
                      {!required && <option value="">不启用</option>}
                      {availableModels.map((model) => (
                        <option key={model.id} value={model.model_key}>
                          {model.display_name}
                        </option>
                      ))}
                    </select>
                    {modelPolicy[modelKey] && (
                      <select
                        aria-label={`${label}推理强度`}
                        value={modelPolicy[effortKey]}
                        onChange={(event) =>
                          onModelPolicyChange({ [effortKey]: event.target.value })
                        }
                      >
                        {(selectedModel?.supported_efforts ?? []).map((effort) => (
                          <option key={effort} value={effort}>
                            推理强度{EFFORT_LABELS[effort] ?? effort}
                          </option>
                        ))}
                      </select>
                    )}
                  </label>
                );
              })}
            </div>
            <div className="task-runtime-override">
              <label className="task-config-choice">
                本次初筛抽检比例（%）
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={modelPolicy.cheap_audit_percent ?? 5}
                  onChange={(event) =>
                    onModelPolicyChange({
                      cheap_audit_percent: Number(event.target.value),
                    })
                  }
                />
                <small>修改后自动更新检查结果，仅用于本次任务。</small>
              </label>
            </div>
          </div>
        </details>
      </div>
      {children}
    </section>
  );
}
