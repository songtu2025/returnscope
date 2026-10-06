import { ListChecks } from "@phosphor-icons/react";
import { EmptyState, StatusBadge } from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";

/** @typedef {import("../../shared/api/reviewBatchContracts").LegacyReviewRecord} LegacyReviewRecord */
/** @typedef {{status: string, rows: LegacyReviewRecord[], selectedId: string | null, onStatus: (status: string) => void, onSelectId: (id: string) => void}} LegacyReviewListProps */

/** @param {{row: LegacyReviewRecord, selectedId: string | null, onSelectId: LegacyReviewListProps["onSelectId"]}} props */
function LegacyReviewRow({ row, selectedId, onSelectId }) {
  return (
    <button
      key={row.id}
      className={selectedId === row.id ? "active" : ""}
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
export function LegacyReviewList({ status, rows, selectedId, onStatus, onSelectId }) {
  return (
    <aside className="review-list">
      <div className="segmented">
        <button
          className={status === "pending" ? "active" : ""}
          onClick={() => onStatus("pending")}
        >
          待复核
        </button>
        <button
          className={status === "resolved" ? "active" : ""}
          onClick={() => onStatus("resolved")}
        >
          已处理
        </button>
      </div>
      <div className="review-scroll">
        {rows.length === 0 && (
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
          />
        ))}
      </div>
    </aside>
  );
}
