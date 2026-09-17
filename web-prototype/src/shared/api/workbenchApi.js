import { queryString, request } from "./request";

/** @typedef {import("./workbenchContracts").WorkbenchSummary} WorkbenchSummary */

export const workbenchApi = {
  /** @returns {Promise<WorkbenchSummary>} */
  summary: (limit = 5, options = {}) =>
    request(`/api/workbench/summary${queryString({ limit })}`, options),
};
