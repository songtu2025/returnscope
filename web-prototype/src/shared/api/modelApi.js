import { API_BASE, request } from "./request";

/** @typedef {object} ModelPayload */
/** @typedef {ReturnType<typeof request>} ModelRequest */
/** @typedef {import("./systemSettingsContracts").ModelConnection} ModelConnection */
/** @typedef {import("./systemSettingsContracts").ModelPreference} ModelPreference */
/** @typedef {import("./systemSettingsContracts").ConfigVersion} ConfigVersion */
/** @typedef {import("./systemSettingsContracts").CatalogModel} CatalogModel */
/** @typedef {import("./systemSettingsContracts").ValidationRun} ValidationRun */

/**
 * @type {{
 *   configs: () => Promise<ModelConnection[]>,
 *   modelPreference: () => Promise<ModelPreference | null>,
 *   saveModelPreference: (payload: ModelPayload) => Promise<ModelPreference>,
 *   createConfig: (payload: ModelPayload) => Promise<ConfigVersion>,
 *   discardConfig: (id: string) => ModelRequest,
 *   createModel: (connectionId: string, payload: ModelPayload) => Promise<CatalogModel>,
 *   discoverModels: (connectionId: string) => Promise<{count: number}>,
 *   updateModel: (id: string, payload: ModelPayload) => Promise<CatalogModel>,
 *   validateModel: (id: string, effort?: string | null) => ModelRequest,
 *   startModelValidation: (id: string, effort?: string | null) => Promise<ValidationRun>,
 *   validateConfig: (id: string) => ModelRequest,
 *   startConfigValidation: (id: string) => Promise<ValidationRun>,
 *   activeValidation: (connectionId: string) => Promise<ValidationRun | null>,
 *   validationRun: (id: string) => Promise<ValidationRun>,
 *   validationEventUrl: (id: string) => string,
 *   publishConfig: (id: string) => ModelRequest
 * }}
 */
export const modelApi = {
  configs: () => request("/api/configs"),
  modelPreference: () => request("/api/model-preferences/me"),
  saveModelPreference: (payload) =>
    request("/api/model-preferences/me", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  createConfig: (payload) =>
    request("/api/configs", { method: "POST", body: JSON.stringify(payload) }),
  discardConfig: (id) => request(`/api/configs/${id}`, { method: "DELETE" }),
  createModel: (connectionId, payload) =>
    request(`/api/connections/${connectionId}/models`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  discoverModels: (connectionId) =>
    request(`/api/connections/${connectionId}/models/discover`, {
      method: "POST",
    }),
  updateModel: (id, payload) =>
    request(`/api/models/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  validateModel: (id, effort = null) =>
    request(`/api/models/${id}/validate`, {
      method: "POST",
      body: JSON.stringify({ effort }),
    }),
  startModelValidation: (id, effort = null) =>
    request(`/api/models/${id}/validation-runs`, {
      method: "POST",
      body: JSON.stringify({ effort }),
    }),
  validateConfig: (id) => request(`/api/configs/${id}/validate`, { method: "POST" }),
  startConfigValidation: (id) =>
    request(`/api/configs/${id}/validation-runs`, { method: "POST" }),
  activeValidation: (connectionId) =>
    request(`/api/connections/${connectionId}/active-validation`),
  validationRun: (id) => request(`/api/validation-runs/${id}`),
  validationEventUrl: (id) => `${API_BASE}/api/validation-runs/${id}/events`,
  publishConfig: (id) => request(`/api/configs/${id}/publish`, { method: "POST" }),
};
