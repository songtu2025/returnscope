import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import {
  EMPTY_POLICY,
  policyForConnection,
  policyForModel,
  verifiedModels,
} from "./modelPreferencePolicy";
/** @typedef {import("../../shared/api/systemSettingsContracts").ModelConnection} ModelConnection */
/** @typedef {import("../../shared/api/systemSettingsContracts").CatalogModel} CatalogModel */
/** @typedef {import("../../shared/api/systemSettingsContracts").ModelPreference} ModelPreference */
/** @typedef {import("../../shared/api/systemSettingsContracts").PipelineModelKey} PipelineModelKey */
/** @typedef {import("../../shared/api/systemSettingsContracts").PipelineEffortKey} PipelineEffortKey */

/** @typedef {(message: string, tone?: string) => void} Notify */
/** @typedef {import("react").Dispatch<import("react").SetStateAction<ModelPreference>>} SetPolicy */
/** @param {Notify} notify @param {(value: boolean) => void} setLoading @param {(value: ModelConnection[]) => void} setConnections @param {SetPolicy} setPolicy */
async function loadPreference(notify, setLoading, setConnections, setPolicy) {
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
    notify(error instanceof Error ? error.message : "模型偏好读取失败", "error");
  } finally {
    setLoading(false);
  }
}

/** @param {ModelPreference} policy @param {Notify} notify @param {SetPolicy} setPolicy @param {(value: boolean) => void} setSaving */
async function savePreference(policy, notify, setPolicy, setSaving) {
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
    notify(error instanceof Error ? error.message : "模型偏好保存失败", "error");
  } finally {
    setSaving(false);
  }
}

/** @param {Notify} notify */
export function useModelPreference(notify) {
  const [connections, setConnections] = useState(/** @type {ModelConnection[]} */ ([]));
  const [policy, setPolicy] = useState(/** @type {ModelPreference} */ (EMPTY_POLICY));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(
    () => loadPreference(notify, setLoading, setConnections, setPolicy),
    [notify],
  );
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

  /** @param {PipelineModelKey} field @param {string} value */
  const updateModel = (field, value) => {
    const model = modelByKey.get(value);
    setPolicy((current) => policyForModel(current, field, value, model));
  };
  const save = () => savePreference(policy, notify, setPolicy, setSaving);
  return { connections, policy, loading, saving, models, setPolicy, updateModel, save };
}
