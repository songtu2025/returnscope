import { useId, useState } from "react";
import { ArrowRight } from "@phosphor-icons/react";
import { STATUS_LABELS } from "../../constants";
import { formatTime } from "../../lib/presentation";

/** @typedef {import("../../shared/api/dataManagementContracts").DatasetReference} DatasetReference */
/** @typedef {import("../../app/navigation").Navigate} Navigate */

/** @param {{items: DatasetReference[], onNavigate?: Navigate}} props */
export function DatasetReferenceTable({ items, onNavigate }) {
  return (
    <div className="dataset-reference-table-wrap">
      <table className="dataset-reference-table" aria-label="任务引用列表">
        <thead>
          <tr>
            <th scope="col">任务名称</th>
            <th scope="col">引用资料</th>
            <th scope="col">状态</th>
            <th scope="col">创建人</th>
            <th scope="col">创建时间</th>
            <th scope="col">操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <ReferenceRow
              key={`${item.task_id}-${item.reference_type}`}
              item={item}
              onNavigate={onNavigate}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** @param {{item: DatasetReference, onNavigate?: Navigate}} props */
function ReferenceRow({ item, onNavigate }) {
  const [expanded, setExpanded] = useState(false);
  const detailId = useId();
  return (
    <>
      <tr>
        <td>
          <b>{item.title || `任务 #${item.task_id}`}</b>
        </td>
        <td>{item.reference_type === "returns" ? "退货明细" : "产品信息"}</td>
        <td>
          {
            /** @type {Record<string, string>} */ (STATUS_LABELS)[item.status ?? ""] ??
              item.status ??
              "未提供状态"
          }
        </td>
        <td>{item.owner?.name || "未提供创建人"}</td>
        <td>
          <time>{formatTime(item.created_at)}</time>
        </td>
        <td className="dataset-reference-actions">
          <button
            className="text-button"
            onClick={() =>
              onNavigate?.("analysis-tasks", { kind: "task", id: item.task_id })
            }
          >
            查看任务 <ArrowRight size={14} />
          </button>
          <button
            className="text-button"
            aria-controls={detailId}
            aria-expanded={expanded}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? "收起输入资料" : "任务输入资料"}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="dataset-reference-details">
          <td colSpan={6}>
            <div id={detailId}>
              <SnapshotFields value={item.version_snapshot} />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

/** @param {{value?: Record<string, unknown>}} props */
function SnapshotFields({ value }) {
  const entries = Object.entries(value ?? {}).filter(
    ([key]) => !["version", "version_id"].includes(key),
  );
  if (!entries.length) return <p>未提供快照明细</p>;
  return (
    <dl className="snapshot-field-list">
      {entries.map(([key, fieldValue]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>
            {fieldValue && typeof fieldValue === "object"
              ? JSON.stringify(fieldValue)
              : String(fieldValue ?? "未提供")}
          </dd>
        </div>
      ))}
    </dl>
  );
}
