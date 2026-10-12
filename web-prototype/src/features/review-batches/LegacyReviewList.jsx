import { ListChecks, WarningCircle } from "@phosphor-icons/react";
import { EmptyState, InlineLoading, StatusBadge } from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";

/** @typedef {import("../../shared/api/reviewBatchContracts").LegacyReviewRecord} LegacyReviewRecord */
/** @typedef {{status: string, rows: LegacyReviewRecord[], selectedId: string | null, onStatus: (status: string) => void, onSelectId: (id: string) => void, loading: boolean, showLoading?: boolean, error: string, onReload: () => Promise<void>, disabled: boolean}} LegacyReviewListProps */

/** @param {{row: LegacyReviewRecord, selectedId: string | null, onSelectId: LegacyReviewListProps["onSelectId"], disabled: boolean}} props */
function LegacyReviewRow({ row, selectedId, onSelectId, disabled }) {
  return (
    <button
      key={row.id}
      className={selectedId === row.id ? "active" : ""}
      disabled={disabled}
      onClick={() => onSelectId(row.id)}
    >
      <div>
        <StatusBadge value={row.classification.status} />
        <time>{formatTime(row.updated_at)}</time>
      </div>
      <p>{row.comment}</p>
      <small>
        {row.task_title} · {row.owner_name}
      </small>
    </button>
  );
}

/** @param {LegacyReviewListProps} props */
export function LegacyReviewList({
  status,
  rows,
  selectedId,
  onStatus,
  onSelectId,
  loading,
  showLoading = true,
  error,
  onReload,
  disabled,
}) {
  return (
    <aside className="review-list" aria-busy={loading}>
      <div className="segmented">
        <button
          className={status === "pending" ? "active" : ""}
          onClick={() => onStatus("pending")}
          disabled={disabled}
        >
          待复核
        </button>
        <button
          className={status === "resolved" ? "active" : ""}
          onClick={() => onStatus("resolved")}
          disabled={disabled}
        >
          已处理
        </button>
        <InlineLoading
          label="更新中…"
          compact
          active={showLoading && loading && rows.length > 0}
        />
      </div>
      <div className="review-scroll">
        {loading &&
          !rows.length &&
          (showLoading ? (
            <InlineLoading scope="page" label="正在读取复核记录…" />
          ) : (
            <p className="muted-line">正在读取复核列表…</p>
          ))}
        {error && (
          <EmptyState
            icon={WarningCircle}
            title="复核列表读取失败"
            description={error}
            action={<button onClick={onReload}>重新加载</button>}
          />
        )}
        {!loading && !error && rows.length === 0 && (
          <EmptyState
            icon={ListChecks}
            title="没有记录"
            description={
              status === "pending" ? "当前无需人工复核。" : "尚无已处理记录。"
            }
          />
        )}
        {rows.map((row) => (
          <LegacyReviewRow
            key={row.id}
            row={row}
            selectedId={selectedId}
            onSelectId={onSelectId}
            disabled={disabled}
          />
        ))}
      </div>
    </aside>
  );
}
