/** @typedef {import("../../shared/api/systemSettingsContracts").ModelConnection} ModelConnection */
/** @typedef {import("../../shared/api/systemSettingsContracts").ModelPreference} ModelPreference */
/** @typedef {import("./analysisDashboardContracts").InsightModel} InsightModel */

/** @param {ModelConnection[]} configs @returns {InsightModel[]} */
export function insightModels(configs) {
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
export function preferredInsightModel(configs, models, preference) {
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
