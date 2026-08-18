export function insightModels(configs) {
  const output = [];
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

export function preferredInsightEffort(model) {
  const efforts = model?.supported_efforts ?? [];
  if (efforts.includes("high")) return "high";
  if (efforts.includes("medium")) return "medium";
  return efforts[0] || "high";
}
