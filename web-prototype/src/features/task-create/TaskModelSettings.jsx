import { CaretDown } from "@phosphor-icons/react";
import { EFFORT_LABELS } from "../../constants";

/** @typedef {import("./taskCreateContracts").AvailableModel} AvailableModel */
/** @typedef {import("./taskCreateContracts").PublishedConfig} PublishedConfig */
/** @typedef {import("./taskCreateContracts").TaskForm} TaskForm */
/** @typedef {import("./taskCreateContracts").TaskModelPolicy} TaskModelPolicy */
/** @typedef {"cheap_model" | "primary_model" | "secondary_model"} ModelKey */
/** @typedef {"cheap_effort" | "primary_effort" | "secondary_effort"} EffortKey */
/** @typedef {readonly [string, ModelKey, EffortKey, boolean]} ModelStage */
/**
 * @typedef {{form: TaskForm, publishedConfigs: PublishedConfig[], selectedConfig?: PublishedConfig, availableModels: AvailableModel[], modelPolicy: TaskModelPolicy, onConnectionChange: (configId: string) => void, onModelPolicyChange: (changes: Record<string, string | number>) => void}} TaskModelSettingsProps
 */

/** @type {readonly ModelStage[]} */
const MODEL_STAGES = [
  ["低成本初筛", "cheap_model", "cheap_effort", false],
  ["主分析", "primary_model", "primary_effort", true],
  ["风险复核", "secondary_model", "secondary_effort", false],
];

/** @param {string} effort */
function effortLabel(effort) {
  if (effort === "low" || effort === "medium" || effort === "high") {
    return EFFORT_LABELS[effort];
  }
  return effort;
}

/** @param {TaskModelSettingsProps} props */
export function TaskModelSettings({
  form,
  publishedConfigs,
  selectedConfig,
  availableModels,
  modelPolicy,
  onConnectionChange,
  onModelPolicyChange,
}) {
  return (
    <details className="task-advanced-settings task-model-settings">
      <TaskModelSummary
        availableModels={availableModels}
        modelPolicy={modelPolicy}
        selectedConfig={selectedConfig}
      />
      <div className="task-advanced-body">
        <TaskModelConnection
          form={form}
          publishedConfigs={publishedConfigs}
          onConnectionChange={onConnectionChange}
        />
        <div className="task-model-policy-grid">
          {MODEL_STAGES.map((stage) => (
            <TaskModelStage
              key={stage[1]}
              stage={stage}
              availableModels={availableModels}
              modelPolicy={modelPolicy}
              onModelPolicyChange={onModelPolicyChange}
            />
          ))}
        </div>
        <TaskSamplingSettings
          modelPolicy={modelPolicy}
          onModelPolicyChange={onModelPolicyChange}
        />
      </div>
    </details>
  );
}

/** @param {Pick<TaskModelSettingsProps, "availableModels" | "modelPolicy" | "selectedConfig">} props */
function TaskModelSummary({ availableModels, modelPolicy, selectedConfig }) {
  return (
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
          {effortLabel(modelPolicy.primary_effort)}
        </small>
        {MODEL_STAGES.filter(
          ([, modelKey, , required]) => !required && modelPolicy[modelKey],
        ).map(([label, modelKey, effortKey]) => (
          <small key={modelKey}>
            {label}：
            {availableModels.find((model) => model.model_key === modelPolicy[modelKey])
              ?.display_name || modelPolicy[modelKey]}
            {" · 推理强度"}
            {effortLabel(modelPolicy[effortKey])}
          </small>
        ))}
      </div>
      <span className="task-model-edit">
        更改设置 <CaretDown size={16} />
      </span>
    </summary>
  );
}

/** @param {Pick<TaskModelSettingsProps, "availableModels" | "modelPolicy" | "onModelPolicyChange"> & {stage: ModelStage}} props */
function TaskModelStage({
  stage: [label, modelKey, effortKey, required],
  availableModels,
  modelPolicy,
  onModelPolicyChange,
}) {
  const selectedModel = availableModels.find(
    (item) => item.model_key === modelPolicy[modelKey],
  );
  return (
    <label className="task-config-choice">
      {label}
      <select
        value={modelPolicy[modelKey] || ""}
        onChange={(event) => {
          const model = availableModels.find(
            (item) => item.model_key === event.target.value,
          );
          onModelPolicyChange({
            [modelKey]: event.target.value,
            [effortKey]: model?.supported_efforts.includes(modelPolicy[effortKey])
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
        <TaskModelEffort
          label={label}
          effortKey={effortKey}
          selectedModel={selectedModel}
          modelPolicy={modelPolicy}
          onModelPolicyChange={onModelPolicyChange}
        />
      )}
    </label>
  );
}

/** @param {Pick<TaskModelSettingsProps, "modelPolicy" | "onModelPolicyChange"> & {label: string, effortKey: EffortKey, selectedModel?: AvailableModel}} props */
function TaskModelEffort({
  label,
  effortKey,
  selectedModel,
  modelPolicy,
  onModelPolicyChange,
}) {
  return (
    <select
      aria-label={`${label}推理强度`}
      value={modelPolicy[effortKey]}
      onChange={(event) => onModelPolicyChange({ [effortKey]: event.target.value })}
    >
      {(selectedModel?.supported_efforts ?? []).map((effort) => (
        <option key={effort} value={effort}>
          推理强度{effortLabel(effort)}
        </option>
      ))}
    </select>
  );
}

/** @param {Pick<TaskModelSettingsProps, "form" | "publishedConfigs" | "onConnectionChange">} props */
function TaskModelConnection({ form, publishedConfigs, onConnectionChange }) {
  return (
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
  );
}

/** @param {Pick<TaskModelSettingsProps, "modelPolicy" | "onModelPolicyChange">} props */
function TaskSamplingSettings({ modelPolicy, onModelPolicyChange }) {
  return (
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
  );
}
