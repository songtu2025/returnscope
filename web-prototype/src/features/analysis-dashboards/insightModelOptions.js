import { api } from "../../api";

/** @typedef {import("../../shared/api/systemSettingsContracts").ModelConnection} ModelConnection */
/** @typedef {import("../../shared/api/systemSettingsContracts").ModelPreference} ModelPreference */
/** @typedef {import("./analysisDashboardContracts").InsightModel} InsightModel */

/** @param {ModelConnection[]} configs @returns {InsightModel[]} */
function insightModels(configs) {
  const output = /** @type {InsightModel[]} */ ([]);
  for (const connection of configs ?? []) {
    for (const model of connection.models ?? []) {
      if (!model.active || model.validation_status !== "validated") continue;
      output.push({
        ...model,
        connection_name: connection.name,
      });
    }
  }
  return output;
}

/** @param {ModelConnection[]} configs @param {InsightModel[]} models @param {ModelPreference | null} preference */
function preferredInsightModel(configs, models, preference) {
  const preferred = models.find(
    (model) =>
      model.connection_id === preference?.connection_id &&
      model.model_key === preference?.primary_model,
  );
  if (preferred) return preferred.id;

  for (const connection of configs ?? []) {
    const activeKey = connection.active_version?.primary_model;
    const active = models.find(
      (model) => model.connection_id === connection.id && model.model_key === activeKey,
    );
    if (active) return active.id;
  }
  return models[0]?.id || "";
}

/** @param {InsightModel | null | undefined} model */
export function preferredInsightEffort(model) {
  const efforts = model?.supported_efforts ?? [];
  if (efforts.includes("high")) return "high";
  if (efforts.includes("medium")) return "medium";
  return efforts[0] || "high";
}

/** 两个报告入口复用同一模型目录读取，偏好失败仍按已发布配置选择。 */
export async function loadInsightModelOptions() {
  const [configs, preference] = await Promise.allSettled([
    api.configs(),
    typeof api.modelPreference === "function"
      ? api.modelPreference()
      : Promise.resolve(null),
  ]);
  if (configs.status === "rejected") throw configs.reason;
  const models = insightModels(configs.value);
  return {
    models,
    preferredModelId: preferredInsightModel(
      configs.value,
      models,
      preference.status === "fulfilled" ? preference.value : null,
    ),
  };
}

/** @param {import("./analysisDashboardContracts").InsightGenerationForm} current @param {{models: InsightModel[], preferredModelId: string}} options */
export function insightFormForOptions(current, options) {
  const model =
    options.models.find((item) => item.id === current.modelId) ??
    options.models.find((item) => item.id === options.preferredModelId);
  return {
    modelId: model?.id || "",
    effort: model?.supported_efforts?.includes(current.effort)
      ? current.effort
      : preferredInsightEffort(model),
  };
}
