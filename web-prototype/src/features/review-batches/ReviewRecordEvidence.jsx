import { resultLabelText } from "../../lib/taxonomyPresentation";
import { SemanticResultPanel } from "../classification-results/SemanticResultPanel";
import { REVIEW_ASSESSMENT_FIELDS, reviewAssessmentLabel } from "./reviewAssessment";
import { SemanticReviewLedger } from "./SemanticReviewLedger";
import { values, valueText } from "./reviewRecordPresentation";

/** @param {{value?: import("../../shared/api/reviewBatchContracts").HumanReviewAssessment}} props */
function ReviewAssessmentSummary({ value }) {
  return (
    <section className="review-assessment-summary" aria-label="已保存的复核质量判断">
      <header>
        <b>复核质量判断</b>
        <span>三个维度分别记录</span>
      </header>
      <dl>
        {REVIEW_ASSESSMENT_FIELDS.map((field) => (
          <div key={field.key}>
            <dt>{field.label}</dt>
            <dd>{reviewAssessmentLabel(field, value?.[field.storedKey])}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** @param {{record: import("../../shared/api/reviewBatchContracts").ReviewRecord}} props */
function ReviewBusinessEvidence({ record }) {
  return (
    <section className="review-business-evidence">
      <dl>
        <div>
          <dt>产品名称</dt>
          <dd>{valueText(values(record, "product_names"))}</dd>
        </div>
        <div>
          <dt>Listing</dt>
          <dd>{valueText(values(record, "listings"), "未提供 Listing")}</dd>
        </div>
        <div>
          <dt>产品SKU</dt>
          <dd>{valueText(values(record, "product_skus"))}</dd>
        </div>
        <div>
          <dt>退货SKU（MSKU）</dt>
          <dd>{valueText(values(record, "source_skus"))}</dd>
        </div>
        <div>
          <dt>匹配MSKU</dt>
          <dd>{valueText(values(record, "matched_mskus"), "未匹配")}</dd>
        </div>
        <div>
          <dt>分类单元记录数</dt>
          <dd>{Number(record.record_count || 0).toLocaleString()}</dd>
        </div>
      </dl>
    </section>
  );
}

/** @param {{record: import("../../shared/api/reviewBatchContracts").ReviewRecord}} props */
function ReviewSourceContext({ record }) {
  const classification = record.classification ?? {};
  return (
    <>
      <details className="review-source-context">
        <summary>展开完整原文上下文</summary>
        <blockquote>“{record.comment || "没有评论证据"}”</blockquote>
      </details>

      <details className="review-primary-context">
        <summary>查看完整语义详情</summary>
        <div>
          <span>主因（辅助信息）</span>
          <p>
            {resultLabelText(record, classification.primary_label_codes) ||
              "未形成主因标签"}
          </p>
        </div>
        <SemanticResultPanel record={record} />
      </details>
    </>
  );
}

/** @param {Pick<import("./reviewRecordPresentation").ReviewRecordDrawerProps, "record" | "labels" | "semanticItemReviews" | "addedSemanticItems" | "coverageStatus" | "onSemanticItemReviews" | "onAddedSemanticItems" | "onCoverageStatus"> & {editable: boolean}} props */
export function ReviewRecordEvidence({
  record,
  labels,
  editable,
  semanticItemReviews,
  addedSemanticItems,
  coverageStatus,
  onSemanticItemReviews,
  onAddedSemanticItems,
  onCoverageStatus,
}) {
  const classification = record.classification ?? {};
  return (
    <>
      <ReviewBusinessEvidence record={record} />

      <SemanticReviewLedger
        key={record.id}
        record={record}
        labels={labels}
        editable={editable}
        itemReviews={semanticItemReviews}
        addedItems={addedSemanticItems}
        coverageStatus={coverageStatus}
        onItemReviews={onSemanticItemReviews}
        onAddedItems={onAddedSemanticItems}
        onCoverageStatus={onCoverageStatus}
      />

      <ReviewSourceContext record={record} />

      {!editable && (
        <ReviewAssessmentSummary value={classification.human_review_assessment} />
      )}
    </>
  );
}
