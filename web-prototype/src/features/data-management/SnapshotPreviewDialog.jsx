import { useEffect, useState } from "react";
import { DownloadSimple, Eye, FileCsv, WarningCircle } from "@phosphor-icons/react";
import { InlineLoading, Modal } from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";
import { dataApi } from "../../shared/api/dataApi";

/** @typedef {import("../../shared/api/dataManagementContracts").DatasetSource} DatasetSource */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetVersion} DatasetVersion */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRowsPage} DatasetRowsPage */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRow} DatasetRow */

/** @param {DatasetRow[]} records */
function previewColumns(records) {
  return records.length
    ? Object.keys(records[0]).filter(
        (column) =>
          column !== "_row_index" &&
          records.some((record) => String(record[column] ?? "").trim()),
      )
    : [];
}

/** @param {{snapshot: DatasetVersion, datasetId: string}} props */
function SnapshotPreviewSummary({ snapshot, datasetId }) {
  return (
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
  );
}

/** @param {{records: DatasetRow[], columns: string[]}} props */
function SnapshotPreviewTable({ records, columns }) {
  return (
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
  );
}

/** @param {{preview: DatasetRowsPage | null, error: string, records: DatasetRow[], columns: string[]}} props */
function SnapshotPreviewState({ preview, error, records, columns }) {
  return (
    <>
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
        <SnapshotPreviewTable records={records} columns={columns} />
      ) : (
        <div className="snapshot-preview-message">
          <FileCsv size={20} />
          <b>该快照没有数据</b>
        </div>
      )}
    </>
  );
}

/** @param {{preview: DatasetRowsPage | null, error: string, records: DatasetRow[], columns: string[]}} props */
function SnapshotPreviewContent({ preview, error, records, columns }) {
  return (
    <section className="snapshot-preview-content" aria-label="快照数据预览">
      <header>
        <div>
          <Eye size={18} />
          <b>数据预览</b>
        </div>
        <span>前 10 行</span>
      </header>
      <SnapshotPreviewState
        error={error}
        preview={preview}
        records={records}
        columns={columns}
      />
      {preview && (
        <footer>
          当前预览 {records.length} 行，共{" "}
          {Number(preview.source_total || 0).toLocaleString()} 行；下载可查看完整内容。
        </footer>
      )}
    </section>
  );
}

/** @param {{source: DatasetSource, snapshot: DatasetVersion, onClose: () => void}} props */
export function SnapshotPreviewDialog({ source, snapshot, onClose }) {
  const [preview, setPreview] = useState(/** @type {DatasetRowsPage | null} */ (null));
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
        const errorValue =
          requestError instanceof Error ? requestError : new Error("快照读取失败");
        if (errorValue.name !== "AbortError") setError(errorValue.message);
      });
    return () => controller.abort();
  }, [datasetId, snapshot.version]);

  const records = preview?.records ?? [];
  const columns = previewColumns(records);

  return (
    <Modal
      eyebrow={current ? "当前数据" : "历史数据"}
      title={`${current ? "当前" : "历史"}快照内容`}
      description={`查看 v${snapshot.version} 的真实数据，预览不会修改当前版本。`}
      className="snapshot-preview-modal"
      onClose={onClose}
    >
      <div className="snapshot-preview-body">
        <SnapshotPreviewSummary snapshot={snapshot} datasetId={datasetId} />

        <SnapshotPreviewContent
          preview={preview}
          error={error}
          records={records}
          columns={columns}
        />
      </div>
    </Modal>
  );
}
