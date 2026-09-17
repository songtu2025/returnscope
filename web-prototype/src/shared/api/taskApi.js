import { API_BASE, queryString, request } from "./request";

/**
 * @typedef {Record<string, string | number | boolean | null | undefined>} TaskQuery
 * @typedef {Record<string, unknown>} TaskPayload
 * @typedef {"pause" | "resume" | "cancel"} TaskControlAction
 * @typedef {ReturnType<typeof request>} TaskRequest
 */

/**
 * @type {{
 *   tasks: (filters?: TaskQuery, options?: RequestInit) => TaskRequest,
 *   task: (id: string, options?: RequestInit) => TaskRequest,
 *   preflightTask: (payload: TaskPayload) => TaskRequest,
 *   preflightTaskReplan: (id: string, payload: TaskPayload) => TaskRequest,
 *   replanTask: (id: string, payload: TaskPayload) => TaskRequest,
 *   retryTaskSegment: (id: string, segmentKey: string, payload: TaskPayload) => TaskRequest,
 *   retrySegmentResultPublish: (id: string, segmentId: string, payload: TaskPayload) => TaskRequest,
 *   reorderTaskSegments: (id: string, payload: TaskPayload) => TaskRequest,
 *   setTaskParallelism: (id: string, payload: TaskPayload) => TaskRequest,
 *   controlTaskSegment: (id: string, segmentKey: string, action: TaskControlAction, payload: TaskPayload) => TaskRequest,
 *   analysis: (id: string, filters?: TaskQuery, options?: RequestInit) => TaskRequest,
 *   analysisDownloadUrl: (id: string, filters?: TaskQuery) => string,
 *   renameTask: (id: string, payload: TaskPayload) => TaskRequest,
 *   createTask: (payload: TaskPayload) => TaskRequest,
 *   cancelTask: (id: string, payload: TaskPayload) => TaskRequest,
 *   pauseTask: (id: string, payload: TaskPayload) => TaskRequest,
 *   resumeTask: (id: string, payload: TaskPayload) => TaskRequest,
 *   retryTask: (id: string) => TaskRequest,
 *   archiveTasks: (taskIds: string[], archived: boolean) => TaskRequest,
 *   eventUrl: (taskId: string, after?: number) => string,
 *   downloadUrl: (taskId: string) => string,
 *   segmentDownloadUrl: (taskId: string, segmentKey: string) => string
 * }}
 */
export const taskApi = {
  tasks: (filters = {}, options = {}) =>
    request(`/api/tasks${queryString(filters)}`, options),
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
  archiveTasks: (taskIds, archived) =>
    request("/api/tasks/archive", {
      method: "POST",
      body: JSON.stringify({ task_ids: taskIds, archived }),
    }),
  eventUrl: (taskId, after = 0) =>
    `${API_BASE}/api/tasks/${taskId}/events?after=${after}`,
  downloadUrl: (taskId) => `${API_BASE}/api/tasks/${taskId}/download`,
  segmentDownloadUrl: (taskId, segmentKey) =>
    `${API_BASE}/api/tasks/${taskId}/segments/${encodeURIComponent(segmentKey)}/download`,
};
