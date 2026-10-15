import { API_BASE, request } from "./request";

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
    const response = await fetch(`${API_BASE}/api/result-exports/${job.id}/file`, {
      credentials: "include",
    });
    if (!response.ok) throw new Error("下载失败，请重试；文件过期时请重新生成");
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = job.filename;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
