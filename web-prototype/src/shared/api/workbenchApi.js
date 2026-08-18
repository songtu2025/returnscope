import { queryString, request } from "./request";

export const workbenchApi = {
  summary: (limit = 5, options = {}) =>
    request(`/api/workbench/summary${queryString({ limit })}`, options),
};
