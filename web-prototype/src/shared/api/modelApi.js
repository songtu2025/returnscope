import { API_BASE, request } from "./request";

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
