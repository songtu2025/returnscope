/** @typedef {import("../../shared/api/systemSettingsContracts").ModelConnection} ModelConnection */
/** @typedef {import("../../shared/api/systemSettingsContracts").CatalogModel} CatalogModel */
/** @typedef {import("../../shared/api/systemSettingsContracts").ModelPreference} ModelPreference */
/** @typedef {import("../../shared/api/systemSettingsContracts").PipelineModelKey} PipelineModelKey */
/** @typedef {import("../../shared/api/systemSettingsContracts").PipelineEffortKey} PipelineEffortKey */

/** @type {ModelPreference} */
export const EMPTY_POLICY = {
  connection_id: "",
  cheap_model: "",
  cheap_effort: "low",
  primary_model: "",
  primary_effort: "medium",
  secondary_model: "",
  secondary_effort: "high",
  cheap_audit_percent: 5,
};

/** @param {ModelConnection | null | undefined} connection @returns {CatalogModel[]} */
export function verifiedModels(connection) {
  return (connection?.models ?? []).filter(
    (model) => model.active && model.validation_status === "validated",
  );
}

/** @param {ModelConnection | null | undefined} connection @param {ModelPreference} [current] @returns {ModelPreference} */
export function policyForConnection(connection, current = EMPTY_POLICY) {
  const models = verifiedModels(connection);
  const firstModel = models[0]?.model_key ?? "";
  /** @param {string} modelKey */
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

/** @param {ModelPreference} current @param {PipelineModelKey} field @param {string} value @param {CatalogModel | undefined} model */
export function policyForModel(current, field, value, model) {
  const effortField = /** @type {PipelineEffortKey} */ (
    field.replace("_model", "_effort")
  );
  return {
    ...current,
    [field]: value,
    [effortField]: model?.supported_efforts.includes(current[effortField])
      ? current[effortField]
      : (model?.supported_efforts[0] ?? current[effortField]),
  };
}
