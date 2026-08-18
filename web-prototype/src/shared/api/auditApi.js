import { queryString, request } from "./request";

export const auditApi = {
  logs: (filters = {}, options = {}) =>
    request(`/api/audit-logs${queryString(filters)}`, options),
};
