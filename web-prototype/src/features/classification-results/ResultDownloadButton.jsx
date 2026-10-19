import { useId, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { DownloadSimple } from "@phosphor-icons/react";
import { resultExportApi } from "../../shared/api/resultExportApi";
import { errorStatus } from "../../shared/api/requestErrors";

/** @typedef {import("../../shared/api/resultExportApi").ResultExport} ResultExport */

/** @param {string} key */
function savedJobId(key) {
  const saved = localStorage.getItem(key);
  if (!saved) return null;
  // 兼容已发布版本只保存任务编号的格式，查询一次后更新为带有效期的缓存。
  if (!saved.startsWith("{")) return saved;
  const value = JSON.parse(saved);
  if (value.expires_at * 1000 > Date.now()) return String(value.id);
  localStorage.removeItem(key);
  return null;
}

/** @param {{job?: ResultExport, error: unknown, failure: string, generationFailed: boolean, resultMissing: boolean, label: string}} state */
function downloadFeedback({
  job,
  error,
  failure,
  generationFailed,
  resultMissing,
  label,
}) {
  const feedback = {
    missing: false,
    queryFailed: false,
    actionLabel: label,
    message: "",
  };
  const status = Number(errorStatus(error));
  if (resultMissing || status === 404)
    return {
      ...feedback,
      missing: true,
      actionLabel: "无法下载",
      message: "分类结果不存在，请刷新页面",
    };
  if (status === 410) return feedback;
  if (error)
    return {
      ...feedback,
      queryFailed: true,
      actionLabel: "重新查询状态",
      message:
        status === 403
          ? "暂无下载权限，请重新查询或联系管理员"
          : "无法查询导出状态，请重新查询",
    };
  if (failure)
    return {
      ...feedback,
      actionLabel: generationFailed ? "重试导出" : "重试下载",
      message: failure,
    };
  if (job?.status === "failed")
    return {
      ...feedback,
      actionLabel: "重试导出",
      message: job.error || "导出生成失败，请重试",
    };
  return feedback;
}

/** @param {{versionId?: string, versionIds?: string[], label?: string, compact?: boolean}} props */
export function ResultDownloadButton({
  versionId,
  versionIds,
  label = "下载",
  compact = false,
}) {
  const versions = versionIds ?? [String(versionId)];
  const storageKey = `result-export:${versions.join(":")}`;
  const [jobId, setJobId] = useState(() => savedJobId(storageKey));
  const [submitting, setSubmitting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState("");
  const [generationFailed, setGenerationFailed] = useState(false);
  const [resultMissing, setResultMissing] = useState(false);
  const submitLock = useRef(false);
  const feedbackId = useId();
  const autoDownload = useRef(false);
  const { mutate } = useSWRConfig();
  const {
    data: job,
    error,
    mutate: refreshJob,
    isLoading,
  } = useSWR(
    jobId ? ["result-export", jobId] : null,
    ([, id]) => resultExportApi.get(id),
    {
      refreshInterval: (value) =>
        value && ["queued", "running"].includes(value.status) ? 2000 : 0,
      shouldRetryOnError: false,
      onError: (error) => {
        if (Number(errorStatus(error)) === 410) clearSavedJob();
      },
      onSuccess: (value) => {
        remember(value);
        if (value.status === "ready" && autoDownload.current) {
          autoDownload.current = false;
          void save(value);
        }
      },
    },
  );

  function clearSavedJob() {
    localStorage.removeItem(storageKey);
    setJobId(null);
    autoDownload.current = false;
  }

  /** @param {ResultExport} value */
  function remember(value) {
    localStorage.setItem(
      storageKey,
      JSON.stringify({ id: value.id, expires_at: value.expires_at }),
    );
  }

  /** @param {unknown} error @param {boolean} [generation] */
  function reportFailure(error, generation = false) {
    setResultMissing(Number(errorStatus(error)) === 404);
    setGenerationFailed(generation);
    setFailure(error instanceof Error ? error.message : "下载失败，请重试");
  }

  /** @param {ResultExport} value */
  async function save(value, prepareAgain = true) {
    setSaving(true);
    try {
      await resultExportApi.save(value);
    } catch (error) {
      if (Number(errorStatus(error)) === 410 && prepareAgain) {
        // 文件可能在核对与下载之间过期；沿用同次下载意图，只重新准备一次。
        clearSavedJob();
        try {
          await prepare(false);
        } catch (failure) {
          reportFailure(failure, true);
        }
      } else {
        reportFailure(error);
      }
    } finally {
      setSaving(false);
    }
  }

  async function prepare(prepareAgain = true) {
    // 每次主动下载仍由服务端核对最新数据、复用缓存或生成文件，不重跑语义分析。
    const next = await resultExportApi.create(versions);
    remember(next);
    autoDownload.current = next.status !== "ready";
    setJobId(next.id);
    await mutate(["result-export", next.id], next, { revalidate: true });
    if (next.status === "ready") await save(next, prepareAgain);
  }

  async function start() {
    if (submitLock.current) return;
    submitLock.current = true;
    setSubmitting(true);
    setFailure("");
    setGenerationFailed(false);
    try {
      await prepare();
    } catch (error) {
      reportFailure(error, true);
    } finally {
      submitLock.current = false;
      setSubmitting(false);
    }
  }

  async function retryQuery() {
    setSubmitting(true);
    setFailure("");
    try {
      await refreshJob();
    } catch {
      // 查询错误由 SWR 保留，用户可继续查询同一个导出任务。
    } finally {
      setSubmitting(false);
    }
  }

  const pending = !error && job && ["queued", "running"].includes(job.status);
  const { missing, queryFailed, message, actionLabel } = downloadFeedback({
    job,
    error,
    failure,
    generationFailed,
    resultMissing,
    label,
  });
  const busy = submitting || saving || Boolean(pending) || isLoading;
  return (
    <span className="result-download-control">
      <button
        type="button"
        className={`secondary-button ${compact ? "compact-button" : ""}`}
        disabled={busy || missing}
        aria-busy={busy}
        aria-describedby={message ? feedbackId : undefined}
        onClick={() => void (queryFailed ? retryQuery() : start())}
      >
        <DownloadSimple size={compact ? 15 : 18} />
        <span className="result-download-label">
          <span className="result-download-reserve" aria-hidden="true">
            {label}
          </span>
          <span>
            {submitting || saving ? "正在处理" : pending ? "正在生成" : actionLabel}
          </span>
        </span>
      </button>
      {message && (
        <small id={feedbackId} role="alert">
          {message}
        </small>
      )}
    </span>
  );
}
