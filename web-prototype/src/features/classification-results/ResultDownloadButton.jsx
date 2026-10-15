import { useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { DownloadSimple } from "@phosphor-icons/react";
import { resultExportApi } from "../../shared/api/resultExportApi";

/** @typedef {import("../../shared/api/resultExportApi").ResultExport} ResultExport */

/** @param {{versionId?: string, versionIds?: string[], label?: string, compact?: boolean}} props */
export function ResultDownloadButton({
  versionId,
  versionIds,
  label = "下载",
  compact = false,
}) {
  const versions = versionIds ?? [String(versionId)];
  const storageKey = `result-export:${versions.join(":")}`;
  const [jobId, setJobId] = useState(() => localStorage.getItem(storageKey));
  const [submitting, setSubmitting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState("");
  const autoDownload = useRef(false);
  const { mutate } = useSWRConfig();
  const { data: job, error } = useSWR(
    jobId ? ["result-export", jobId] : null,
    ([, id]) => resultExportApi.get(id),
    {
      refreshInterval: (value) =>
        value && ["queued", "running"].includes(value.status) ? 2000 : 0,
      shouldRetryOnError: false,
      onSuccess: (value) => {
        if (value.status === "ready" && autoDownload.current) {
          autoDownload.current = false;
          void save(value);
        }
      },
    },
  );

  /** @param {ResultExport} value */
  async function save(value) {
    setSaving(true);
    try {
      await resultExportApi.save(value);
    } catch (error) {
      setFailure(error instanceof Error ? error.message : "下载失败，请重试");
    } finally {
      setSaving(false);
    }
  }

  async function start() {
    setSubmitting(true);
    setFailure("");
    try {
      // 每次主动下载先核对当前数据；刷新页面只恢复已有任务，不重新生成。
      const next = await resultExportApi.create(versions);
      localStorage.setItem(storageKey, next.id);
      autoDownload.current = next.status !== "ready";
      setJobId(next.id);
      await mutate(["result-export", next.id], next, { revalidate: true });
      if (next.status === "ready") await save(next);
    } catch (error) {
      setFailure(error instanceof Error ? error.message : "提交导出失败，请重试");
    } finally {
      setSubmitting(false);
    }
  }

  const pending = !error && job && ["queued", "running"].includes(job.status);
  const message = failure || (error ? "无法查询导出状态，请重试" : job?.error);
  return (
    <span className="result-download-control">
      <button
        type="button"
        className={`secondary-button ${compact ? "compact-button" : ""}`}
        disabled={submitting || saving || Boolean(pending)}
        aria-busy={submitting || saving || Boolean(pending)}
        onClick={() => void start()}
      >
        <DownloadSimple size={compact ? 15 : 18} />
        <span className="result-download-label">
          <span className="result-download-reserve" aria-hidden="true">
            {label}
          </span>
          <span>
            {submitting || saving
              ? "正在处理"
              : pending
                ? "正在生成"
                : message
                  ? "重试下载"
                  : label}
          </span>
        </span>
      </button>
      {message && <small role="alert">{message}</small>}
    </span>
  );
}
