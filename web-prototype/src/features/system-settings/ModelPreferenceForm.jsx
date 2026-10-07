import { policyForConnection } from "./modelPreferencePolicy";
/** @typedef {import("../../shared/api/systemSettingsContracts").ModelConnection} ModelConnection */
/** @typedef {import("../../shared/api/systemSettingsContracts").CatalogModel} CatalogModel */
/** @typedef {import("../../shared/api/systemSettingsContracts").ModelPreference} ModelPreference */
/** @typedef {import("../../shared/api/systemSettingsContracts").PipelineModelKey} PipelineModelKey */
/** @typedef {import("../../shared/api/systemSettingsContracts").PipelineEffortKey} PipelineEffortKey */

/** @typedef {ReturnType<typeof import("./useModelPreference").useModelPreference>} PreferenceFormProps */
/** @type {Array<[string, string]>} */
const EFFORT_OPTIONS = [
  ["low", "低"],
  ["medium", "中"],
  ["high", "高"],
];

/** @type {Array<{label: string, note: string, modelField: PipelineModelKey, effortField: PipelineEffortKey, optional?: boolean}>} */
const POLICY_ROWS = [
  {
    label: "低成本初筛",
    note: "可选；用于快速筛选。抽检比例在模型服务或创建任务时设置。",
    modelField: "cheap_model",
    effortField: "cheap_effort",
    optional: true,
  },
  {
    label: "主分析",
    note: "必选；用于完成主要语义分析。",
    modelField: "primary_model",
    effortField: "primary_effort",
  },
  {
    label: "风险复核",
    note: "可选；用于高风险或需要复核的结果。",
    modelField: "secondary_model",
    effortField: "secondary_effort",
    optional: true,
  },
];

/** @param {PreferenceFormProps} props */
function PreferenceConnection({ connections, policy, setPolicy }) {
  return (
    <label className="model-preference-field">
      <span>模型服务连接</span>
      <select
        value={policy.connection_id}
        onChange={(event) => {
          const nextConnection = connections.find(
            (item) => item.id === event.target.value,
          );
          setPolicy((current) => policyForConnection(nextConnection, current));
        }}
      >
        {connections.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
          </option>
        ))}
      </select>
    </label>
  );
}

/** @param {PreferenceFormProps} props */
function PreferenceRows({ models, policy, updateModel, setPolicy }) {
  return !models.length ? (
    <p className="model-preference-empty">
      此连接没有已启用且验证通过的模型，暂时不能保存策略。
    </p>
  ) : (
    <div className="model-preference-rows">
      {POLICY_ROWS.map((row) => (
        <PolicyRow
          key={row.modelField}
          {...row}
          policy={policy}
          models={models}
          onModelChange={updateModel}
          onEffortChange={(field, value) =>
            setPolicy((current) => ({ ...current, [field]: value }))
          }
        />
      ))}
    </div>
  );
}

/** @param {PreferenceFormProps} props */
export function ModelPreferenceForm(props) {
  const { connections, policy, models, saving, save } = props;
  return (
    <section className="content-card model-preference-card">
      {!connections.length ? (
        <p className="model-preference-empty">
          暂无已发布的模型服务。请联系系统管理员完成接入、模型验证与发布。
        </p>
      ) : (
        <>
          <PreferenceConnection {...props} />
          <PreferenceRows {...props} />
        </>
      )}
      <footer>
        <button
          className="primary-button"
          onClick={save}
          disabled={saving || !models.length || !policy.primary_model}
        >
          {saving ? "保存中…" : "保存为我的默认策略"}
        </button>
      </footer>
    </section>
  );
}

/**
 * @param {{
 *   label: string,
 *   note: string,
 *   modelField: PipelineModelKey,
 *   effortField: PipelineEffortKey,
 *   optional?: boolean,
 *   policy: ModelPreference,
 *   models: CatalogModel[],
 *   onModelChange: (field: PipelineModelKey, value: string) => void,
 *   onEffortChange: (field: PipelineEffortKey, value: string) => void,
 * }} props
 */
function PolicyRow({
  label,
  note,
  modelField,
  effortField,
  optional = false,
  policy,
  models,
  onModelChange,
  onEffortChange,
}) {
  const selected = models.find((item) => item.model_key === policy[modelField]);
  return (
    <div className="model-preference-row">
      <div>
        <b>{label}</b>
        <span>{note}</span>
      </div>
      <select
        aria-label={`${label}模型`}
        value={policy[modelField]}
        onChange={(event) => onModelChange(modelField, event.target.value)}
      >
        {optional && <option value="">不使用</option>}
        {models.map((model) => (
          <option key={model.id} value={model.model_key}>
            {model.display_name}
          </option>
        ))}
      </select>
      <select
        aria-label={`${label}推理强度`}
        value={policy[effortField]}
        disabled={!selected}
        onChange={(event) => onEffortChange(effortField, event.target.value)}
      >
        {(selected?.supported_efforts ?? []).map((effort) => (
          <option key={effort} value={effort}>
            推理强度 {EFFORT_OPTIONS.find(([key]) => key === effort)?.[1] ?? effort}
          </option>
        ))}
      </select>
    </div>
  );
}
