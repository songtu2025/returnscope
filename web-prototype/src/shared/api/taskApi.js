import { API_BASE, queryString, request } from "./request";

export const taskApi = {
  tasks: (options = {}) => request("/api/tasks", options),
  task: (id, options = {}) => request(`/api/tasks/${id}`, options),
  preflightTask: (payload) =>
    request("/api/tasks/preflight", { method: "POST", body: JSON.stringify(payload) }),
  preflightTaskReplan: (id, payload) =>
    request(`/api/tasks/${id}/replan/preflight`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  replanTask: (id, payload) =>
    request(`/api/tasks/${id}/replan`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  retryTaskSegment: (id, segmentKey, payload) =>
    request(`/api/tasks/${id}/segments/${encodeURIComponent(segmentKey)}/retry`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  retrySegmentResultPublish: (id, segmentId, payload) =>
    request(
      `/api/tasks/${id}/segments/${encodeURIComponent(segmentId)}/retry-result-publish`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  reorderTaskSegments: (id, payload) =>
    request(`/api/tasks/${id}/segments/order`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  setTaskParallelism: (id, payload) =>
    request(`/api/tasks/${id}/parallelism`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  controlTaskSegment: (id, segmentKey, action, payload) =>
    request(`/api/tasks/${id}/segments/${encodeURIComponent(segmentKey)}/${action}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  analysis: (id, filters = {}, options = {}) =>
    request(`/api/tasks/${id}/analysis${queryString(filters)}`, options),
  analysisDownloadUrl: (id, filters = {}) =>
    `${API_BASE}/api/tasks/${id}/analysis/download${queryString(filters)}`,
  renameTask: (id, payload) =>
    request(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  createTask: (payload) =>
    request("/api/tasks", { method: "POST", body: JSON.stringify(payload) }),
  cancelTask: (id, payload) =>
    request(`/api/tasks/${id}/cancel`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  pauseTask: (id, payload) =>
    request(`/api/tasks/${id}/pause`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  resumeTask: (id, payload) =>
    request(`/api/tasks/${id}/resume`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  retryTask: (id) => request(`/api/tasks/${id}/retry`, { method: "POST" }),
  eventUrl: (taskId, after = 0) =>
    `${API_BASE}/api/tasks/${taskId}/events?after=${after}`,
  downloadUrl: (taskId) => `${API_BASE}/api/tasks/${taskId}/download`,
  segmentDownloadUrl: (taskId, segmentKey) =>
    `${API_BASE}/api/tasks/${taskId}/segments/${encodeURIComponent(segmentKey)}/download`,
};
