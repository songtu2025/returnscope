import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../../api";
import { InlineLoading, PageHeading } from "../../components/SharedUi";

const EFFORT_OPTIONS = [
  ["low", "低"],
  ["medium", "中"],
  ["high", "高"],
];

const EMPTY_POLICY = {
  connection_id: "",
  cheap_model: "",
  cheap_effort: "low",
  primary_model: "",
  primary_effort: "medium",
  secondary_model: "",
  secondary_effort: "high",
  cheap_audit_percent: 5,
};

function verifiedModels(connection) {
  return (connection?.models ?? []).filter(
    (model) => model.active && model.validation_status === "validated",
  );
}

function policyForConnection(connection, current = EMPTY_POLICY) {
  const models = verifiedModels(connection);
  const firstModel = models[0]?.model_key ?? "";
  const keepIfAvailable = (modelKey) =>
    models.some((model) => model.model_key === modelKey) ? modelKey : firstModel;
  return {
    ...EMPTY_POLICY,
    ...current,
    connection_id: connection?.id ?? "",
    cheap_audit_percent:
      connection?.active_version?.cheap_audit_percent ??
      current.cheap_audit_percent ??
      EMPTY_POLICY.cheap_audit_percent,
    cheap_model: current.cheap_model ? keepIfAvailable(current.cheap_model) : "",
    primary_model: keepIfAvailable(current.primary_model),
    secondary_model: current.secondary_model
      ? keepIfAvailable(current.secondary_model)
      : "",
  };
}

export function ModelPreferencePage({ notify }) {
  const [connections, setConnections] = useState([]);
  const [policy, setPolicy] = useState(EMPTY_POLICY);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [serviceConnections, preference] = await Promise.all([
        api.configs(),
        api.modelPreference(),
      ]);
      const published = serviceConnections.filter((item) => item.active_version_id);
      const selected =
        published.find((item) => item.id === preference?.connection_id) ??
        published[0] ??
        null;
      setConnections(published);
      setPolicy(policyForConnection(selected, preference ?? EMPTY_POLICY));
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    load();
  }, [load]);

  const connection = useMemo(
    () => connections.find((item) => item.id === policy.connection_id) ?? null,
    [connections, policy.connection_id],
  );
  const models = useMemo(() => verifiedModels(connection), [connection]);
  const modelByKey = useMemo(
    () => new Map(models.map((model) => [model.model_key, model])),
    [models],
  );

  const updateModel = (field, value) => {
    const model = modelByKey.get(value);
    const effortField = field.replace("_model", "_effort");
    setPolicy((current) => ({
      ...current,
      [field]: value,
      [effortField]: model?.supported_efforts.includes(current[effortField])
        ? current[effortField]
        : (model?.supported_efforts[0] ?? current[effortField]),
    }));
  };

  const save = async () => {
    if (!policy.primary_model) {
      notify("请选择主分析模型", "error");
      return;
    }
    setSaving(true);
    try {
      const value = await api.saveModelPreference({
        ...policy,
        cheap_model: policy.cheap_model || null,
        secondary_model: policy.secondary_model || null,
      });
      setPolicy(value);
      notify("默认模型策略已保存", "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <InlineLoading label="正在读取个人模型偏好…" />;

  return (
    <div className="standard-page model-preference-page">
      <PageHeading
        eyebrow="个人默认设置"
        title="我的模型偏好"
        description="新建任务会默认带入此策略；你仍可在创建任务时针对本次执行调整。"
      />
      <section className="content-card model-preference-card">
        {!connections.length ? (
          <p className="model-preference-empty">
            暂无已发布的模型服务。请联系系统管理员完成接入、模型验证与发布。
          </p>
        ) : (
          <>
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
            {!models.length ? (
              <p className="model-preference-empty">
                此连接没有已启用且验证通过的模型，暂时不能保存策略。
              </p>
            ) : (
              <div className="model-preference-rows">
                <PolicyRow
                  label="低成本初筛"
                  note="可选；用于快速筛选。抽检比例在模型服务或创建任务时设置。"
                  modelField="cheap_model"
                  effortField="cheap_effort"
                  optional
                  policy={policy}
                  models={models}
                  onModelChange={updateModel}
                  onEffortChange={(field, value) =>
                    setPolicy((current) => ({ ...current, [field]: value }))
                  }
                />
                <PolicyRow
                  label="主分析"
                  note="必选；用于完成主要语义分析。"
                  modelField="primary_model"
                  effortField="primary_effort"
                  policy={policy}
                  models={models}
                  onModelChange={updateModel}
                  onEffortChange={(field, value) =>
                    setPolicy((current) => ({ ...current, [field]: value }))
                  }
                />
                <PolicyRow
                  label="风险复核"
                  note="可选；用于高风险或需要复核的结果。"
                  modelField="secondary_model"
                  effortField="secondary_effort"
                  optional
                  policy={policy}
                  models={models}
                  onModelChange={updateModel}
                  onEffortChange={(field, value) =>
                    setPolicy((current) => ({ ...current, [field]: value }))
                  }
                />
              </div>
            )}
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
    </div>
  );
}

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
