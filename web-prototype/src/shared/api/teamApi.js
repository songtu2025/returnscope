import { request } from "./request";

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
  createUser: (payload) =>
    request("/api/users", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateUserStatus: (id, payload) =>
    request(`/api/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
};
