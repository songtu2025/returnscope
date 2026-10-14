import useSWR, { useSWRConfig } from "swr";
import { useDataRefresh } from "../../hooks/useDataRefresh";
import { useProtectedData } from "../../hooks/useProtectedData";
import { MANAGED_REFRESH_OPTIONS } from "../../shared/refreshPolicy";
import { refreshServerState } from "../../shared/serverState";
import { useEffect, useMemo, useState } from "react";
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
const EMPTY_CONNECTIONS = /** @type {ModelConnection[]} */ ([]);

/** @typedef {(message: string, tone?: string) => void} Notify */
/** @typedef {import("react").Dispatch<import("react").SetStateAction<ModelPreference>>} SetPolicy */
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
    return value;
  } catch (error) {
    notify(error instanceof Error ? error.message : "模型偏好保存失败", "error");
  } finally {
    setSaving(false);
  }
}

/** @param {Notify} notify */
export function useModelPreference(notify) {
  const { mutate: mutateCache } = useSWRConfig();
  const [policy, setPolicyState] = useState(
    /** @type {ModelPreference} */ (EMPTY_POLICY),
  );
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const {
    data,
    error: loadError,
    isLoading,
    isValidating,
    mutate,
  } = useSWR(
    ["settings", "model-preference"],
    async () => {
      const [allConnections, preference] = await Promise.all([
        api.configs(),
        api.modelPreference(),
      ]);
      const connections = allConnections.filter((item) => item.active_version_id);
      const selected =
        connections.find((item) => item.id === preference?.connection_id) ??
        connections[0] ??
        null;
      return {
        connections,
        policy: policyForConnection(selected, preference ?? EMPTY_POLICY),
      };
    },
    MANAGED_REFRESH_OPTIONS,
  );
  const displayed = useProtectedData(data, dirty || saving, "model-preference");
  const connections = displayed?.connections ?? EMPTY_CONNECTIONS;
  useEffect(() => {
    if (displayed && !dirty && !saving) setPolicyState(displayed.policy);
  }, [displayed, dirty, saving]);
  useDataRefresh(() => mutate(), { loading: isLoading || isValidating });
  const loading = isLoading && !data;
  const error =
    loadError instanceof Error
      ? loadError.message
      : loadError
        ? "模型偏好读取失败"
        : "";
  const load = () => mutate();
  /** @type {SetPolicy} */
  const setPolicy = (value) => {
    setDirty(true);
    setPolicyState(value);
  };

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
  const save = async () => {
    const value = await savePreference(policy, notify, setPolicyState, setSaving);
    if (!value) return;
    await mutate(
      { connections: data?.connections ?? [], policy: value },
      { revalidate: false },
    );
    setDirty(false);
    void refreshServerState(mutateCache, ["task-create"]).catch(() =>
      notify("偏好已保存，关联配置更新失败，可重试", "error"),
    );
  };
  return {
    connections,
    hasData: Boolean(data),
    policy,
    loading,
    saving,
    error,
    load,
    models,
    setPolicy,
    updateModel,
    save,
    dirty,
    reset: () => {
      setPolicyState(displayed?.policy ?? EMPTY_POLICY);
      setDirty(false);
    },
  };
}
