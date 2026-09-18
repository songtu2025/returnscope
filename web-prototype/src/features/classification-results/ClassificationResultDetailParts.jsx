import { CaretRight } from "@phosphor-icons/react";

import { resultState, resultStateLabel } from "./resultActionPolicy";
import { SemanticStatusBadge } from "./SemanticResultPanel";
import { semanticRecordStatus } from "./semanticResultPresentation";
import { resultLabelText } from "../../lib/taxonomyPresentation";

/**
 * @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultDrilldownItemResponse} ClassificationResultDrilldownItem
 * @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultRecordResponse} ClassificationResultRecord
 */

/**
 * @param {{ label: string, value: number, note?: string, tone?: string }} props
 */
export function SummaryMetric({ label, value, note = "", tone = "" }) {
  return (
    <div className={tone ? `is-${tone}` : ""}>
      <span>{label}</span>
      <b>{Number(value || 0).toLocaleString()}</b>
      {note && <small>{note}</small>}
    </div>
  );
}

/**
 * @param {{
 *   title: string,
 *   items: ClassificationResultDrilldownItem[],
 *   selected: string,
 *   onSelect: (value: string) => void,
 *   emptyLabel?: string,
 *   emptyTitle?: string,
 *   emptyDescription?: string,
 *   limit?: number
 * }} props
 */
export function DrilldownColumn({
  title,
  items,
  selected,
  onSelect,
  emptyLabel = "未标注",
  emptyTitle = "暂无数据",
  emptyDescription = "",
  limit = 12,
}) {
  return (
    <div className="drilldown-column">
      <b>{title}</b>
      <div>
        {items.length === 0 && (
          <span className="drilldown-empty">
            <b>{emptyTitle}</b>
            {emptyDescription && (
              <>
                <br />
                {emptyDescription}
              </>
            )}
          </span>
        )}
        {items.slice(0, limit).map((item) => {
          const value = item.value ?? "";
          const label =
            item.label_path?.join(" → ") || item.label_name || value || emptyLabel;
          return (
            <button
              key={`${title}-${value || "empty"}`}
              className={selected === value ? "active" : ""}
              onClick={() => onSelect(value)}
            >
              <span title={label}>{label}</span>
              <b>{Number(item.record_count || 0).toLocaleString()}</b>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/**
 * @param {{
 *   record: ClassificationResultRecord,
 *   analysisContext: string,
 *   onOpen: (trigger: HTMLButtonElement) => void
 * }} props
 */
export function ResultRecordRow({ record, analysisContext, onOpen }) {
  const isUserFeedback = analysisContext === "user_feedback";
  const problems = record.problem_labels ?? [];
  const labels = isUserFeedback
    ? [
        ...new Set([
          ...problems,
          ...(record.classification?.positive_label_codes ?? []),
        ]),
      ]
    : problems;
  return (
    <article className="result-record-row" role="row">
      <div>
        <b>{record.order_id || "未提供"}</b>
        <span>{record.return_date || `源记录 ${record.source_row}`}</span>
      </div>
      <div>
        <b>{record.source_sku || "未提供"}</b>
        <span>匹配MSKU：{record.matched_msku || "未匹配"}</span>
      </div>
      <div>
        <b>{record.product_name || "未提供"}</b>
        <span>产品SKU：{record.product_sku || "未提供"}</span>
      </div>
      <div>
        <b>{record.reason || "未提供"}</b>
        <span>
          {record.comment || (isUserFeedback ? "没有反馈正文" : "没有退货评论")}
        </span>
      </div>
      <div>
        <span className={`result-quality-badge ${resultState(record)}`}>
          {resultStateLabel(record)}
        </span>
        <SemanticStatusBadge status={semanticRecordStatus(record)} />
        <b>
          {resultLabelText(record, labels) ||
            (isUserFeedback ? "未形成语义标签" : "未形成问题标签")}
        </b>
      </div>
      <div className="result-row-actions">
        <button
          className="secondary-button compact-button"
          onClick={(event) => onOpen(event.currentTarget)}
        >
          查看证据
          <CaretRight size={15} />
        </button>
      </div>
    </article>
  );
}
