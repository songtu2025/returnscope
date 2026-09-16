import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CaretDown,
  CaretLeft,
  CaretRight,
  CheckCircle,
  ClockCounterClockwise,
  Database,
  DownloadSimple,
  Eye,
  FileCsv,
  Funnel,
  HardDrives,
  MagnifyingGlass,
  ShieldCheck,
  UploadSimple,
  WarningCircle,
} from "@phosphor-icons/react";

import {
  EmptyState,
  InlineLoading,
  Modal,
  PageHeading,
} from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";
import { dataApi } from "../../shared/api/dataApi";
import { ReturnImportDialog } from "../task-create/ReturnImportDialog";
import { DataAssetTabs } from "./DataAssetTabs";

const PAGE_SIZE = 20;
const SNAPSHOT_PAGE_SIZE = 5;

export function ReturnDataAssetsPage({ route, notify, onRouteChange }) {
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const [detailsBySource, setDetailsBySource] = useState({});
  const [expandedOverride, setExpandedOverride] = useState(null);

  const loadSources = useCallback(async () => {
    setLoading(true);
    try {
      const items = canonicalSources(await dataApi.managedDatasets("returns"));
      setSources(items);
      setDetailsBySource({});
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  useEffect(() => {
    setPage(1);
  }, [query, status]);

  const filteredSources = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return sources.filter((source) => {
      const sourceStatus = dataStatus(source).value;
      if (status !== "all" && sourceStatus !== status) return false;
      if (!keyword) return true;
      return [
        sourceDisplayName(source),
        sourceScopeLabel(source),
        ...(source.quality?.stores ?? []),
      ].some((value) => String(value).toLowerCase().includes(keyword));
    });
  }, [query, sources, status]);

  const totalPages = Math.max(1, Math.ceil(filteredSources.length / PAGE_SIZE));
  const visibleSources = filteredSources.slice(
    (page - 1) * PAGE_SIZE,
    page * PAGE_SIZE,
  );
  const requestedSource = sources.find((source) =>
    source.member_ids.includes(route.query.dataset),
  );
  const defaultExpandedId =
    visibleSources.find((source) => source.id === requestedSource?.id)?.id ||
    visibleSources[0]?.id ||
    "";
  const expandedId = expandedOverride ?? defaultExpandedId;

  useEffect(() => {
    setExpandedOverride(null);
  }, [route.query.dataset]);

  useEffect(() => {
    const source = sources.find((item) => item.id === expandedId);
    if (!source || detailsBySource[expandedId]) return undefined;
    const controller = new AbortController();
    Promise.all(
      source.member_ids.map((id) =>
        dataApi.dataset(id, {
          include: "versions,imports",
          signal: controller.signal,
        }),
      ),
    )
      .then((members) => {
        if (!controller.signal.aborted) {
          setDetailsBySource((current) => ({
            ...current,
            [expandedId]: mergeSourceDetails(source, members),
          }));
        }
      })
      .catch((error) => {
        if (error.name !== "AbortError") notify(error.message, "error");
      });
    return () => controller.abort();
  }, [detailsBySource, expandedId, notify, sources]);
  const availableCount = sources.filter(
    (source) => dataStatus(source).value === "available",
  ).length;
  const latestUpdate = sources.reduce(
    (latest, source) =>
      String(source.updated_at || "") > String(latest || "")
        ? source.updated_at
        : latest,
    "",
  );

  const selectSource = (source) => {
    if (source.id === expandedId) {
      setExpandedOverride("");
      return;
    }
    setExpandedOverride(source.id);
    onRouteChange({ view: "returns", dataset: source.id, tab: "" });
  };

  const finishImport = async (result) => {
    setUploadOpen(false);
    await loadSources();
    if (result.dataset?.id) {
      onRouteChange({ view: "returns", dataset: result.dataset.id, tab: "" });
    }
    notify(result.duplicate ? "该批次已存在，已定位到原数据源" : "退货数据源已更新");
  };

  return (
    <div className="standard-page data-page returns-assets-page">
      <PageHeading
        eyebrow="数据资产"
        title="退货数据源管理"
        description="管理可复用的退货数据源和最近导入状态。"
        action={
          <button className="primary-button" onClick={() => setUploadOpen(true)}>
            <UploadSimple size={18} />
            导入新批次
          </button>
        }
      />
      <DataAssetTabs
        current="returns"
        onChange={(view) => onRouteChange({ view, dataset: "", tab: "" })}
      />

      {loading ? (
        <section className="content-card returns-assets-loading">
          <InlineLoading label="正在读取退货数据源…" />
        </section>
      ) : sources.length === 0 ? (
        <EmptyState
          icon={FileCsv}
          title="尚未建立退货数据源"
          description="导入首个批次后，系统会识别业务范围并建立可复用的数据源。"
          action={
            <button className="primary-button" onClick={() => setUploadOpen(true)}>
              <UploadSimple size={17} />
              导入首个批次
            </button>
          }
        />
      ) : (
        <section className="returns-registry" aria-label="退货数据源清单">
          <header className="returns-registry-toolbar">
            <div className="returns-registry-summary">
              <span>
                <Database size={18} />
                <b>{sources.length} 个数据源</b>
              </span>
              <i aria-hidden="true">•</i>
              <strong>{availableCount} 个当前可用</strong>
              <i aria-hidden="true">•</i>
              <em>{sources.length - availableCount} 个需关注</em>
              <i aria-hidden="true">•</i>
              <span>最近导入：{formatTime(latestUpdate)}</span>
            </div>
            <div className="returns-registry-filters">
              <label className="returns-registry-search">
                <MagnifyingGlass size={17} />
                <input
                  aria-label="搜索退货数据源"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="搜索数据源或业务范围"
                />
              </label>
              <label className="returns-registry-filter">
                <Funnel size={17} />
                <select
                  aria-label="按数据状态筛选"
                  value={status}
                  onChange={(event) => setStatus(event.target.value)}
                >
                  <option value="all">全部状态</option>
                  <option value="available">当前可用</option>
                  <option value="attention">需关注</option>
                </select>
              </label>
            </div>
          </header>

          {visibleSources.length ? (
            <div className="returns-registry-table" role="table">
              <div className="returns-registry-head" role="row">
                <span>数据源</span>
                <span>业务范围</span>
                <span>当前数据</span>
                <span>最近导入</span>
                <span>数据状态</span>
                <span>被任务使用</span>
                <span>操作</span>
              </div>
              {visibleSources.map((source) => {
                const expanded = source.id === expandedId;
                const sourceState = dataStatus(source);
                return (
                  <article
                    className={`returns-registry-record ${expanded ? "expanded" : ""}`}
                    key={source.id}
                  >
                    <div className="returns-registry-row" role="row">
                      <div className="returns-registry-name">
                        <Database size={19} weight="duotone" />
                        <b>{sourceDisplayName(source)}</b>
                      </div>
                      <span>{sourceScopeLabel(source)}</span>
                      <b>{Number(source.row_count || 0).toLocaleString()} 行</b>
                      <span>{formatTime(source.updated_at)}</span>
                      <span className={`returns-source-status ${sourceState.value}`}>
                        {sourceState.value === "available" ? (
                          <CheckCircle size={18} weight="fill" />
                        ) : (
                          <WarningCircle size={18} weight="fill" />
                        )}
                        <span>
                          <b>{sourceState.label}</b>
                          <small>{sourceState.description}</small>
                        </span>
                      </span>
                      <span>
                        {Number(source.task_reference_count || 0).toLocaleString()}{" "}
                        个任务
                      </span>
                      <button
                        className="returns-detail-button"
                        aria-expanded={expanded}
                        onClick={() => selectSource(source)}
                      >
                        {expanded ? "收起详情" : "查看详情"}
                        <CaretDown size={17} />
                      </button>
                    </div>
                    {expanded &&
                      (detailsBySource[source.id] ? (
                        <SourceDetail
                          source={detailsBySource[source.id]}
                          notify={notify}
                          onStorageChanged={loadSources}
                          initiallyShowTrace={["imports", "snapshots"].includes(
                            route.query.tab,
                          )}
                        />
                      ) : (
                        <InlineLoading label="正在读取数据源详情…" />
                      ))}
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="returns-registry-empty">
              <MagnifyingGlass size={23} />
              <b>没有符合条件的数据源</b>
              <span>请修改搜索词或数据状态。</span>
            </div>
          )}

          <footer className="returns-registry-footer">
            <span>共 {filteredSources.length} 个数据源</span>
            {totalPages > 1 && (
              <div>
                <button
                  aria-label="上一页"
                  disabled={page === 1}
                  onClick={() => setPage((current) => current - 1)}
                >
                  <CaretLeft size={16} />
                </button>
                <b>{page}</b>
                <span>/ {totalPages}</span>
                <button
                  aria-label="下一页"
                  disabled={page === totalPages}
                  onClick={() => setPage((current) => current + 1)}
                >
                  <CaretRight size={16} />
                </button>
              </div>
            )}
          </footer>
        </section>
      )}

      {uploadOpen && (
        <ReturnImportDialog
          purpose="asset"
          onClose={() => setUploadOpen(false)}
          onDone={finishImport}
        />
      )}
    </div>
  );
}

function SourceDetail({ source, notify, onStorageChanged, initiallyShowTrace }) {
  const [showTrace, setShowTrace] = useState(initiallyShowTrace);
  const latestImport = source.imports?.[0];
  const currentVersion = source.versions?.find((item) => item.id === source.version_id);
  const metrics = latestImport
    ? [
        ["导入方式", importModeLabel(latestImport.mode)],
        ["原始数据", `${Number(latestImport.row_count || 0).toLocaleString()} 行`],
        [
          "写入当前数据",
          `${Number(latestImport.imported_row_count || 0).toLocaleString()} 行`,
        ],
        [
          "跳过重复",
          `${Number(latestImport.skipped_row_count || 0).toLocaleString()} 行`,
        ],
        ["导入人", latestImport.creator_name || "未记录"],
        ["备注", latestImport.change_note || "未填写"],
      ]
    : [
        ["记录类型", "历史快照"],
        ["当前数据", `${Number(source.row_count || 0).toLocaleString()} 行`],
        [
          "有效评论",
          `${Number(source.quality?.valid_comment_rows || 0).toLocaleString()} 行`,
        ],
        [
          "匹配键完整度",
          `${Number(source.quality?.matching_key_ready_rate || 0).toLocaleString()}%`,
        ],
        ["维护人", currentVersion?.creator_name || source.creator_name || "未记录"],
        ["原始文件", currentVersion?.original_name || source.original_name || "未记录"],
      ];

  return (
    <section className="returns-source-expanded-detail" aria-label="数据源详情">
      <header>
        <div>
          <b>{latestImport ? "最近导入摘要" : "当前数据摘要"}</b>
          <span>
            {latestImport
              ? `${latestImport.original_name} · ${formatTime(latestImport.created_at)}`
              : "该数据源建立于结构化导入记录启用之前"}
          </span>
        </div>
        <button className="text-button" onClick={() => setShowTrace((value) => !value)}>
          <ClockCounterClockwise size={16} />
          {showTrace ? "收起追溯记录" : "查看追溯记录"}
        </button>
      </header>
      <dl className="returns-import-metrics">
        {metrics.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {showTrace && (
        <SourceTrace
          source={source}
          notify={notify}
          onStorageChanged={onStorageChanged}
        />
      )}
    </section>
  );
}

function SourceTrace({ source, notify, onStorageChanged }) {
  const [selectedSnapshot, setSelectedSnapshot] = useState(null);
  const [snapshotPage, setSnapshotPage] = useState(1);
  const versions = source.versions ?? [];
  const snapshotPages = Math.max(1, Math.ceil(versions.length / SNAPSHOT_PAGE_SIZE));
  const visibleVersions = versions.slice(
    (snapshotPage - 1) * SNAPSHOT_PAGE_SIZE,
    snapshotPage * SNAPSHOT_PAGE_SIZE,
  );

  useEffect(() => {
    if (snapshotPage > snapshotPages) setSnapshotPage(snapshotPages);
  }, [snapshotPage, snapshotPages]);

  return (
    <>
      <SnapshotStorageOverview
        source={source}
        notify={notify}
        onStorageChanged={onStorageChanged}
      />
      <div className="returns-source-trace">
        <section>
          <h3>导入批次</h3>
          {source.imports?.length ? (
            source.imports.slice(0, 5).map((item) => (
              <article key={item.id}>
                <FileCsv size={18} />
                <span>
                  <b>{item.original_name}</b>
                  <small>
                    {importModeLabel(item.mode)} · {formatTime(item.created_at)}
                  </small>
                </span>
                <strong>{Number(item.row_count || 0).toLocaleString()} 行</strong>
              </article>
            ))
          ) : (
            <p>暂无结构化导入记录。</p>
          )}
        </section>
        <section>
          <h3>完整快照（{versions.length}）</h3>
          {versions.length ? (
            visibleVersions.map((item) => {
              const current = item.id === source.version_id;
              return (
                <button
                  className="returns-snapshot-row"
                  key={item.id}
                  type="button"
                  aria-label={`查看${current ? "当前" : "历史"}快照内容：${item.original_name || `版本 ${item.version}`}`}
                  onClick={() => setSelectedSnapshot(item)}
                >
                  <ClockCounterClockwise size={18} />
                  <span>
                    <b>{current ? "当前快照" : "历史快照"}</b>
                    <small>
                      {item.original_name || "未记录原文件名"} · v{item.version}
                    </small>
                  </span>
                  <strong>{Number(item.row_count || 0).toLocaleString()} 行</strong>
                  <span className="returns-snapshot-action">
                    查看内容
                    <CaretRight size={14} />
                  </span>
                </button>
              );
            })
          ) : (
            <p>暂无完整快照。</p>
          )}
          {snapshotPages > 1 && (
            <footer className="snapshot-pagination">
              <span>
                第 {snapshotPage} / {snapshotPages} 页
              </span>
              <div>
                <button
                  type="button"
                  aria-label="上一页快照"
                  disabled={snapshotPage === 1}
                  onClick={() => setSnapshotPage((value) => value - 1)}
                >
                  <CaretLeft size={15} />
                </button>
                <button
                  type="button"
                  aria-label="下一页快照"
                  disabled={snapshotPage === snapshotPages}
                  onClick={() => setSnapshotPage((value) => value + 1)}
                >
                  <CaretRight size={15} />
                </button>
              </div>
            </footer>
          )}
        </section>
      </div>
      {selectedSnapshot && (
        <SnapshotPreviewDialog
          key={selectedSnapshot.id}
          source={source}
          snapshot={selectedSnapshot}
          onClose={() => setSelectedSnapshot(null)}
        />
      )}
    </>
  );
}

function SnapshotStorageOverview({ source, notify, onStorageChanged }) {
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

function SnapshotPreviewDialog({ source, snapshot, onClose }) {
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");
  const datasetId = snapshot.dataset_id || source.id;
  const current = snapshot.id === source.version_id;

  useEffect(() => {
    const controller = new AbortController();
    dataApi
      .datasetRows(
        datasetId,
        "",
        0,
        10,
        { version: snapshot.version },
        { signal: controller.signal },
      )
      .then(setPreview)
      .catch((requestError) => {
        if (requestError.name !== "AbortError") setError(requestError.message);
      });
    return () => controller.abort();
  }, [datasetId, snapshot.version]);

  const records = preview?.records ?? [];
  const columns = records.length
    ? Object.keys(records[0]).filter(
        (column) =>
          column !== "_row_index" &&
          records.some((record) => String(record[column] ?? "").trim()),
      )
    : [];

  return (
    <Modal
      eyebrow={current ? "当前数据" : "历史数据"}
      title={`${current ? "当前" : "历史"}快照内容`}
      description={`查看 v${snapshot.version} 的真实数据，预览不会修改当前版本。`}
      className="snapshot-preview-modal"
      onClose={onClose}
    >
      <div className="snapshot-preview-body">
        <div className="snapshot-preview-summary">
          <dl>
            <div>
              <dt>原始文件</dt>
              <dd>{snapshot.original_name || "未记录"}</dd>
            </div>
            <div>
              <dt>快照版本</dt>
              <dd>v{snapshot.version}</dd>
            </div>
            <div>
              <dt>数据量</dt>
              <dd>{Number(snapshot.row_count || 0).toLocaleString()} 行</dd>
            </div>
            <div>
              <dt>生成时间</dt>
              <dd>{formatTime(snapshot.created_at)}</dd>
            </div>
            <div>
              <dt>创建人</dt>
              <dd>{snapshot.creator_name || "未记录"}</dd>
            </div>
            <div>
              <dt>变更说明</dt>
              <dd>{snapshot.change_note || "未填写"}</dd>
            </div>
          </dl>
          <a
            className="secondary-button snapshot-download-button"
            href={dataApi.datasetDownloadUrl(datasetId, snapshot.version)}
            download
          >
            <DownloadSimple size={17} />
            下载此快照
          </a>
        </div>

        <section className="snapshot-preview-content" aria-label="快照数据预览">
          <header>
            <div>
              <Eye size={18} />
              <b>数据预览</b>
            </div>
            <span>前 10 行</span>
          </header>
          {error ? (
            <div className="snapshot-preview-message error">
              <WarningCircle size={20} />
              <b>快照读取失败</b>
              <span>{error}</span>
            </div>
          ) : !preview ? (
            <div className="snapshot-preview-loading">
              <InlineLoading label="正在读取该快照…" />
            </div>
          ) : records.length ? (
            <div className="snapshot-preview-table-wrap">
              <table className="snapshot-preview-table">
                <thead>
                  <tr>
                    <th>#</th>
                    {columns.map((column) => (
                      <th key={column}>{column}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {records.map((record, index) => (
                    <tr key={record._row_index ?? index}>
                      <td>{Number(record._row_index ?? index) + 1}</td>
                      {columns.map((column) => (
                        <td key={column} title={String(record[column] || "")}>
                          {String(record[column] || "—")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="snapshot-preview-message">
              <FileCsv size={20} />
              <b>该快照没有数据</b>
            </div>
          )}
          {preview && (
            <footer>
              当前预览 {records.length} 行，共{" "}
              {Number(preview.source_total || 0).toLocaleString()}{" "}
              行；下载可查看完整内容。
            </footer>
          )}
        </section>
      </div>
    </Modal>
  );
}

function formatBytes(value) {
  let size = Number(value || 0);
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  const digits = unitIndex === 0 || size >= 10 ? 0 : 1;
  return `${size.toFixed(digits)} ${units[unitIndex]}`;
}

function canonicalSources(items) {
  const sources = new Map();
  items.forEach((item) => {
    const key = item.source_key || item.id;
    const source = sources.get(key);
    if (source) {
      source.member_ids.push(item.id);
    } else {
      sources.set(key, { ...item, member_ids: [item.id] });
    }
  });
  return [...sources.values()];
}

function mergeSourceDetails(source, items) {
  const current = items.find((item) => item.id === source.id) || items[0];
  const versions = items
    .flatMap((item) => item.versions ?? [])
    .sort((left, right) => String(right.created_at).localeCompare(left.created_at));
  const notesByVersion = new Map(
    versions.map((item) => [item.id, item.change_note || ""]),
  );
  return {
    ...current,
    member_ids: source.member_ids,
    source_name: sourceDisplayName(source),
    task_reference_count: items.reduce(
      (total, item) => total + Number(item.task_reference_count || 0),
      0,
    ),
    versions,
    imports: items
      .flatMap((item) => item.imports ?? [])
      .map((item) => ({
        ...item,
        change_note:
          item.change_note || notesByVersion.get(item.resulting_version_id) || "",
      }))
      .sort((left, right) => String(right.created_at).localeCompare(left.created_at)),
  };
}

function sourceDisplayName(item) {
  if (item.name) return item.name;
  if (item.source_name) return item.source_name;
  const stores = item.quality?.stores ?? [];
  const brands = [
    ...new Set(
      stores.map((value) => String(value).split(":")[0].trim()).filter(Boolean),
    ),
  ];
  if (brands.length === 1) return `${brands[0]} 退货数据`;
  return "未命名退货数据";
}

function sourceScopeLabel(item) {
  const stores = item.quality?.stores ?? [];
  if (!stores.length) return "未识别";
  return [...new Set(stores.map((value) => String(value)))].join(" · ");
}

function dataStatus(item) {
  const quality = item.quality ?? {};
  const missingStoreRows = Number(quality.missing_store_rows || 0);
  const readyRate = Number(quality.matching_key_ready_rate ?? 100);
  if (missingStoreRows > 0) {
    return {
      value: "attention",
      label: "需关注",
      description: `${missingStoreRows.toLocaleString()} 行缺少店铺/站点`,
    };
  }
  if (readyRate < 100) {
    return {
      value: "attention",
      label: "需关注",
      description: `匹配键完整度 ${readyRate.toLocaleString()}%`,
    };
  }
  return {
    value: "available",
    label: "当前可用",
    description: "数据质量就绪",
  };
}

function importModeLabel(mode) {
  return (
    {
      analyze_only: "仅分析本批",
      create: "首次建立数据源",
      append: "追加数据",
      replace: "替换当前数据",
    }[mode] ?? mode
  );
}
