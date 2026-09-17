import { queryString, request } from "./request";

/** @typedef {import("./systemSettingsContracts").AuditLogPage} AuditLogPage */

export const auditApi = {
  /** @returns {Promise<AuditLogPage>} */
  logs: (filters = {}, options = {}) =>
    request(`/api/audit-logs${queryString(filters)}`, options),
};
