import { request } from "./request";

/** @typedef {import("./generated/classification-results/types.gen").ResultExportResponse} ResultExport */

export const resultExportApi = {
  /** @param {string[]} versionIds @returns {Promise<ResultExport>} */
  create: (versionIds) =>
    request("/api/result-exports", {
      method: "POST",
      body: JSON.stringify({ version_ids: versionIds }),
    }),
  /** @param {string} id @returns {Promise<ResultExport>} */
  get: (id) => request(`/api/result-exports/${id}`),
  /** @param {ResultExport} job */
  async save(job) {
    const file = await request(`/api/result-exports/${job.id}/file`, {}, "blob");
    const url = URL.createObjectURL(file);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = job.filename;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
