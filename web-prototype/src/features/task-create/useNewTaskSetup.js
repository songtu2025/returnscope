import { useDataRefresh } from "../../hooks/useDataRefresh";
import { useProtectedData } from "../../hooks/useProtectedData";
import { MANAGED_REFRESH_OPTIONS } from "../../shared/refreshPolicy";
import { useEffect, useState } from "react";
import useSWR from "swr";

import { api } from "../../api";
import { serverStateKeys } from "../../shared/serverState";
import { resolveTaskModelPolicy, taskConnectionSelection } from "./newTaskPolicy";

/** @typedef {import("./taskCreateContracts").ApiConnection} ApiConnection */
/** @typedef {import("./taskCreateContracts").DataVersion} DataVersion */
/** @typedef {import("./taskCreateContracts").ModelPreference} ModelPreference */
/** @typedef {import("./taskCreateContracts").TaskDraft} TaskDraft */
/** @typedef {import("./taskCreateContracts").TaskForm} TaskForm */
/** @typedef {import("./taskCreateContracts").TaskSystemStatus} TaskSystemStatus */

const taskSetupApi = {
  dataVersions: () => /** @type {Promise<DataVersion[]>} */ (api.dataVersions()),
  configs: () => /** @type {Promise<ApiConnection[]>} */ (api.configs()),
  status: () => /** @type {Promise<TaskSystemStatus>} */ (api.status()),
  modelPreference: () =>
    typeof api.modelPreference === "function"
      ? /** @type {Promise<ModelPreference | null>} */ (api.modelPreference())
      : Promise.resolve(null),
};

async function loadTaskSetup() {
  const [data, connections, status, preference] = await Promise.all([
    taskSetupApi.dataVersions(),
    taskSetupApi.configs(),
    taskSetupApi.status(),
    taskSetupApi.modelPreference(),
  ]);
  return { data, connections, status, preference };
}

/** @param {unknown} error */
function setupErrorMessage(error) {
  return error instanceof Error ? error.message : "暂时无法读取数据与模型配置。";
}

/** @param {TaskDraft | null | undefined} draft */
export function useNewTaskSetup(draft) {
  const [importedVersions, setImportedVersions] = useState(
    /** @type {DataVersion[] | null} */ (null),
  );
  const [form, setForm] = useState(
    /** @type {TaskForm} */ ({
      title: "",
      dataset_version_id: "",
      product_version_id: "",
      config_version_id: "",
      store: "",
      listing: "",
      ...draft?.form,
    }),
  );
  const {
    data: fetchedSetup,
    error,
    isLoading,
    mutate,
  } = useSWR(serverStateKeys.taskCreateSetup, loadTaskSetup, MANAGED_REFRESH_OPTIONS);
  const setup = useProtectedData(
    fetchedSetup,
    Boolean(form.title || form.dataset_version_id || form.store || form.listing),
    "task-setup",
  );
  useDataRefresh(() => mutate(), { loading: isLoading });

  useEffect(() => {
    if (!setup) return;
    const products = setup.data.find((item) => item.kind === "products");
    const activeConfig = setup.connections.find(
      (item) => item.active_version,
    )?.active_version;
    setForm((current) => ({
      ...current,
      product_version_id: setup.data.some(
        (item) =>
          item.kind === "products" && item.version_id === current.product_version_id,
      )
        ? current.product_version_id
        : products?.version_id || "",
      config_version_id:
        current.config_version_id ||
        setup.preference?.config_version_id ||
        activeConfig?.id ||
        "",
      model_policy:
        current.model_policy ||
        (setup.preference
          ? {
              connection_id: setup.preference.connection_id,
              cheap_model: setup.preference.cheap_model,
              cheap_effort: setup.preference.cheap_effort,
              primary_model: setup.preference.primary_model,
              primary_effort: setup.preference.primary_effort,
              secondary_model: setup.preference.secondary_model,
              secondary_effort: setup.preference.secondary_effort,
              cheap_audit_percent: setup.preference.cheap_audit_percent ?? 5,
            }
          : undefined),
    }));
  }, [setup]);

  /** @type {import("react").Dispatch<import("react").SetStateAction<DataVersion[]>>} */
  const setVersions = (next) => {
    const nextVersions =
      typeof next === "function" ? next(importedVersions ?? setup?.data ?? []) : next;
    // 用户主动导入的新数据立即可见，后台读取不能覆盖正在填写的任务草稿。
    setImportedVersions(nextVersions);
    void mutate(
      (current) => {
        if (!current) return current;
        return { ...current, data: nextVersions };
      },
      { revalidate: false },
    );
  };

  const configs = setup?.connections ?? [];
  const { publishedConfigs, selectedConfig, selectedConnection } =
    taskConnectionSelection(configs, form.config_version_id);
  const availableModels = (selectedConnection?.models ?? []).filter(
    (model) => model.active && model.validation_status === "validated",
  );
  const modelPolicy = resolveTaskModelPolicy(configs, form);
  const versions = importedVersions ?? setup?.data ?? [];
  const products = versions.filter((item) => item.kind === "products");
  const selectedProducts = products.find(
    (item) => item.version_id === form.product_version_id,
  );

  return {
    availableModels,
    configs,
    form,
    loadingSetup: !setup && (isLoading || !error),
    modelPolicy,
    products,
    publishedConfigs,
    selectedConfig,
    selectedProducts,
    setForm,
    setSetupAttempt: () => void mutate(),
    setVersions,
    setupError: error ? setupErrorMessage(error) : "",
    system: setup?.status ?? null,
    versions,
  };
}
