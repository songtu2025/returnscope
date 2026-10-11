import Button from "antd/es/button";
import { CaretRight } from "@phosphor-icons/react";
import { resultLabelText } from "../../lib/taxonomyPresentation";
import { SemanticStatusBadge } from "../classification-results/SemanticResultPanel";
import { semanticRecordStatus } from "../classification-results/semanticResultPresentation";
import { values, valueText } from "./reviewRecordPresentation";
export { ReviewRecordDrawer } from "./ReviewRecordDrawer";

/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewRecord} ReviewRecord */
const WORKFLOW_STATUS_LABELS = {
  pending: "待处理",
  resolved: "已处理",
  excluded: "已排除",
};

/**
 * @param {{record: ReviewRecord, onOpen: () => void}} props
 */
export function ReviewRecordRow({ record, onOpen }) {
  const classification = record.classification ?? {};
  const semanticCodes = [
    ...(classification.problem_label_codes ?? []),
    ...(classification.positive_label_codes ?? []),
  ];
  const labelCodes = [
    ...new Set(
      semanticCodes.length ? semanticCodes : (classification.primary_label_codes ?? []),
    ),
  ];
  return (
    <article className="review-record-row" role="row">
      <div>
        <b>{valueText(values(record, "order_ids"))}</b>
        <span>{valueText(values(record, "product_names"))}</span>
        {Number(record.record_count || 0) > 1 && (
          <small>{Number(record.record_count).toLocaleString()} 条退货记录</small>
        )}
      </div>
      <div>
        <b>{valueText(values(record, "listings"), "未提供 Listing")}</b>
        <span>产品SKU：{valueText(values(record, "product_skus"))}</span>
      </div>
      <div>
        <b>{valueText(values(record, "source_skus"))}</b>
        <span>匹配MSKU：{valueText(values(record, "matched_mskus"), "未匹配")}</span>
      </div>
      <div>
        <SemanticStatusBadge status={semanticRecordStatus(record)} />
        <b>{resultLabelText(record, labelCodes) || "未形成标签"}</b>
        <span>{record.comment || "没有评论证据"}</span>
      </div>
      <div>
        <span className={`review-record-status ${record.workflow_status}`}>
          {WORKFLOW_STATUS_LABELS[record.workflow_status] ?? record.workflow_status}
        </span>
        <Button
          size="small"
          icon={<CaretRight size={15} />}
          iconPlacement="end"
          onClick={onOpen}
        >
          查看
        </Button>
      </div>
    </article>
  );
}
