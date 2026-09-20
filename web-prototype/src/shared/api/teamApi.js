import { request } from "./request";

/** @typedef {object} TeamPayload */
/** @typedef {ReturnType<typeof request>} TeamRequest */
/** @typedef {import("./systemSettingsContracts").TeamUser} TeamUser */

/**
 * @type {{
 *   login: (email: string, password: string) => TeamRequest,
 *   logout: () => TeamRequest,
 *   me: () => TeamRequest,
 *   changePassword: (payload: TeamPayload) => TeamRequest,
 *   status: (options?: RequestInit) => TeamRequest,
 *   users: () => Promise<TeamUser[]>,
 *   invitations: () => TeamRequest,
 *   inviteUser: (payload: TeamPayload) => TeamRequest,
 *   resendInvitation: (id: string) => TeamRequest,
 *   revokeInvitation: (id: string) => TeamRequest,
 *   validateInvitation: (token: string) => TeamRequest,
 *   register: (payload: TeamPayload) => TeamRequest,
 *   requestPasswordReset: (email: string) => TeamRequest,
 *   validatePasswordReset: (token: string) => TeamRequest,
 *   completePasswordReset: (payload: TeamPayload) => TeamRequest,
 *   updateUserStatus: (id: string, payload: TeamPayload) => TeamRequest
 * }}
 */
export const teamApi = {
  login: (email, password) =>
    request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  me: () => request("/api/auth/me"),
  changePassword: (payload) =>
    request("/api/auth/password", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  status: (options = {}) => request("/api/system/status", options),
  users: () => request("/api/users"),
  invitations: () => request("/api/invitations"),
  inviteUser: (payload) =>
    request("/api/invitations", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  resendInvitation: (id) =>
    request(`/api/invitations/${id}/resend`, { method: "POST" }),
  revokeInvitation: (id) =>
    request(`/api/invitations/${id}/revoke`, { method: "POST" }),
  validateInvitation: (token) =>
    request("/api/auth/invitations/validate", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),
  register: (payload) =>
    request("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  requestPasswordReset: (email) =>
    request("/api/auth/password-reset/request", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  validatePasswordReset: (token) =>
    request("/api/auth/password-reset/validate", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),
  completePasswordReset: (payload) =>
    request("/api/auth/password-reset/complete", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateUserStatus: (id, payload) =>
    request(`/api/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
};
