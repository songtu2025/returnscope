import { useEffect, useState } from "react";
import {
  CaretLeft,
  CaretRight,
  ClockCounterClockwise,
  FileCsv,
} from "@phosphor-icons/react";
import Button from "antd/es/button";

import { formatTime } from "../../lib/presentation";
import { importModeLabel } from "./returnDataAssetPresentation";
import { SnapshotStorageOverview } from "./ReturnDataAssetStorage";
import { SnapshotPreviewDialog } from "./SnapshotPreviewDialog";

const SNAPSHOT_PAGE_SIZE = 5;

/** @typedef {import("../../shared/api/dataManagementContracts").DatasetSource} DatasetSource */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetVersion} DatasetVersion */
/** @typedef {(message: string, tone?: string) => void} Notify */

/** @param {{source: DatasetSource, notify: Notify, onStorageChanged?: () => void | Promise<void>, initiallyShowTrace?: boolean}} props */
export function SourceDetail({ source, notify, onStorageChanged, initiallyShowTrace }) {
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
        <Button
          type="text"
          className="returns-source-trace-toggle"
          icon={<ClockCounterClockwise size={16} />}
          onClick={() => setShowTrace((value) => !value)}
        >
          {showTrace ? "收起追溯记录" : "查看追溯记录"}
        </Button>
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

/** @param {{source: DatasetSource, notify: Notify, onStorageChanged?: () => void | Promise<void>}} props */
function SourceTrace({ source, notify, onStorageChanged }) {
  const [selectedSnapshot, setSelectedSnapshot] = useState(
    /** @type {DatasetVersion | null} */ (null),
  );
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
