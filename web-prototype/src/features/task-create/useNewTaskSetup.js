import { useEffect, useState } from "react";

import { api } from "../../api";

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

/** @param {unknown} error */
function setupErrorMessage(error) {
  return error instanceof Error ? error.message : "暂时无法读取数据与模型配置。";
}

/** @param {TaskDraft | null | undefined} draft */
export function useNewTaskSetup(draft) {
  const [versions, setVersions] = useState(/** @type {DataVersion[]} */ ([]));
  const [configs, setConfigs] = useState(/** @type {ApiConnection[]} */ ([]));
  const [system, setSystem] = useState(/** @type {TaskSystemStatus | null} */ (null));
  const [loadingSetup, setLoadingSetup] = useState(true);
  const [setupError, setSetupError] = useState("");
  const [setupAttempt, setSetupAttempt] = useState(0);
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

  useEffect(() => {
    setLoadingSetup(true);
    setSetupError("");
    Promise.all([
      taskSetupApi.dataVersions(),
      taskSetupApi.configs(),
      taskSetupApi.status(),
      taskSetupApi.modelPreference
        ? taskSetupApi.modelPreference()
        : Promise.resolve(null),
    ])
      .then(([data, connections, status, preference]) => {
        setVersions(data);
        setConfigs(connections);
        setSystem(status);
        const products = data.find((item) => item.kind === "products");
        const activeConfig = connections.find(
          (item) => item.active_version,
        )?.active_version;
        setForm((current) => ({
          ...current,
          product_version_id: current.product_version_id || products?.version_id || "",
          config_version_id:
            current.config_version_id ||
            preference?.config_version_id ||
            activeConfig?.id ||
            "",
          model_policy:
            current.model_policy ||
            (preference
              ? {
                  connection_id: preference.connection_id,
                  cheap_model: preference.cheap_model,
                  cheap_effort: preference.cheap_effort,
                  primary_model: preference.primary_model,
                  primary_effort: preference.primary_effort,
                  secondary_model: preference.secondary_model,
                  secondary_effort: preference.secondary_effort,
                  cheap_audit_percent: preference.cheap_audit_percent ?? 5,
                }
              : undefined),
        }));
      })
      .catch((error) => setSetupError(setupErrorMessage(error)))
      .finally(() => setLoadingSetup(false));
  }, [setupAttempt]);

  return {
    configs,
    form,
    loadingSetup,
    setForm,
    setSetupAttempt,
    setVersions,
    setupError,
    system,
    versions,
  };
}
