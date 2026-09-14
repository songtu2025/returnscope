import { useEffect, useState } from "react";

import { api } from "../../api";

export function useNewTaskSetup(draft) {
  const [versions, setVersions] = useState([]);
  const [configs, setConfigs] = useState([]);
  const [system, setSystem] = useState(null);
  const [loadingSetup, setLoadingSetup] = useState(true);
  const [setupError, setSetupError] = useState("");
  const [setupAttempt, setSetupAttempt] = useState(0);
  const [form, setForm] = useState({
    title: "",
    dataset_version_id: "",
    product_version_id: "",
    config_version_id: "",
    store: "",
    listing: "",
    ...draft?.form,
  });

  useEffect(() => {
    setLoadingSetup(true);
    setSetupError("");
    Promise.all([
      api.dataVersions(),
      api.configs(),
      api.status(),
      api.modelPreference ? api.modelPreference() : Promise.resolve(null),
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
                }
              : undefined),
        }));
      })
      .catch((error) => setSetupError(error.message || "暂时无法读取数据与模型配置。"))
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
