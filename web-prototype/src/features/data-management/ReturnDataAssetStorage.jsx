import { useCallback, useEffect, useState } from "react";
import { HardDrives, ShieldCheck } from "@phosphor-icons/react";

import { InlineLoading, Modal } from "../../components/SharedUi";
import { dataApi } from "../../shared/api/dataApi";
import { formatBytes } from "./returnDataAssetPresentation";

export function SnapshotStorageOverview({ source, notify, onStorageChanged }) {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");
  const [managementOpen, setManagementOpen] = useState(false);

  const loadSummary = useCallback(
    async (options = {}) => {
      setError("");
      try {
        const result = await dataApi.datasetStorageSummary(
          source.member_ids,
          {},
          options,
        );
        setSummary(result);
      } catch (requestError) {
        if (requestError.name !== "AbortError") setError(requestError.message);
      }
    },
    [source.member_ids],
  );

  useEffect(() => {
    const controller = new AbortController();
    loadSummary({ signal: controller.signal });
    return () => controller.abort();
  }, [loadSummary]);

  return (
    <>
      <section className="snapshot-storage-overview" aria-label="快照存储概览">
        <div className="snapshot-storage-title">
          <HardDrives size={20} weight="duotone" />
          <span>
            <b>快照存储</b>
            <small>当前与任务引用版本受保护，重复内容只保留一份文件。</small>
          </span>
        </div>
        {error ? (
          <button type="button" className="text-button" onClick={() => loadSummary()}>
            读取失败，重试
          </button>
        ) : summary ? (
          <div className="snapshot-storage-metrics">
            <span>
              <small>快照</small>
              <b>{summary.version_count} 个</b>
            </span>
            <span>
              <small>实际占用</small>
              <b>{formatBytes(summary.physical_bytes)}</b>
            </span>
            <span>
              <small>任务保护</small>
              <b>{summary.task_referenced_versions} 个</b>
            </span>
            <span>
              <small>可无损优化</small>
              <b>{formatBytes(summary.dedup_reclaimable_bytes)}</b>
            </span>
          </div>
        ) : (
          <InlineLoading label="正在计算存储占用…" />
        )}
        <button
          type="button"
          className="secondary-button snapshot-storage-manage"
          disabled={!summary}
          onClick={() => setManagementOpen(true)}
        >
          管理存储
        </button>
      </section>
      {managementOpen && summary && (
        <SnapshotStorageDialog
          source={source}
          summary={summary}
          notify={notify}
          onSummaryChange={setSummary}
          onStorageChanged={onStorageChanged}
          onClose={() => setManagementOpen(false)}
        />
      )}
    </>
  );
}

function SnapshotStorageDialog({
  source,
  summary,
  notify,
  onSummaryChange,
  onStorageChanged,
  onClose,
}) {
  const [confirmed, setConfirmed] = useState(false);
  const [saving, setSaving] = useState(false);

  const cleanupStorage = async () => {
    setSaving(true);
    try {
      const result = await dataApi.cleanupDatasetStorage({
        dataset_ids: source.member_ids,
        retention_days: summary.retention_days,
        retain_latest: summary.retain_latest,
      });
      onSummaryChange(result.after);
      notify?.(`已安全释放 ${formatBytes(result.freed_bytes)} 存储空间`);
      onClose();
      await onStorageChanged?.();
    } catch (error) {
      notify?.(error.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      eyebrow="数据资产"
      title="快照存储管理"
      description="合并重复文件，并按保留规则清理不再使用的旧版本。"
      className="snapshot-storage-modal"
      onClose={onClose}
    >
      <div className="snapshot-storage-dialog-body">
        <dl className="snapshot-storage-dialog-metrics">
          <div>
            <dt>完整快照</dt>
            <dd>{summary.version_count} 个</dd>
          </div>
          <div>
            <dt>实际占用</dt>
            <dd>{formatBytes(summary.physical_bytes)}</dd>
          </div>
          <div>
            <dt>重复文件可释放</dt>
            <dd>{formatBytes(summary.dedup_reclaimable_bytes)}</dd>
          </div>
          <div>
            <dt>过期候选</dt>
            <dd>{summary.expired_versions} 个</dd>
          </div>
        </dl>

        <section className="snapshot-retention-policy">
          <div>
            <ShieldCheck size={21} weight="fill" />
            <span>
              <b>系统保护规则</b>
              <small>
                清理操作不会影响当前数据，也不会删除被任务或导入记录引用的版本。
              </small>
            </span>
          </div>
          <ul>
            <li>相同内容合并为一份物理文件，所有历史版本仍可正常查看。</li>
            <li>
              每个数据集至少保留最近 {summary.retain_latest} 个版本；仅清理超过{" "}
              {summary.retention_days} 天且没有引用的旧版本。
            </li>
          </ul>
        </section>

        <label className="snapshot-storage-confirmation">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
          />
          <span>我确认仅执行上述受保护的安全清理规则</span>
        </label>

        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="primary-button"
            disabled={!confirmed || !summary.can_cleanup || saving}
            onClick={cleanupStorage}
          >
            {saving
              ? "正在清理…"
              : summary.can_cleanup
                ? "开始安全清理"
                : "暂无可清理内容"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
