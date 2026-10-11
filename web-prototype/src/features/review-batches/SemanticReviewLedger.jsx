import { CheckCircle, WarningCircle } from "@phosphor-icons/react";
import { ReviewLedgerItem } from "./SemanticReviewItem";
import { SemanticReviewGroups } from "./SemanticReviewGroups";
import { useSemanticLedger } from "./useSemanticLedger";

/** @typedef {import("./semanticLedgerContracts").SemanticReviewLedgerItem} SemanticReviewLedgerItem */

/** @param {import("./semanticLedgerContracts").SemanticLedgerProps} props */
export function SemanticReviewLedger(props) {
  const context = { ...props, ...useSemanticLedger(props) };
  const { record, labels, items, reviewFor, displayedSummary } = context;

  /** @param {SemanticReviewLedgerItem} item */
  const renderItem = (item) => {
    const review = reviewFor(item);
    return (
      <ReviewLedgerItem
        key={item.id}
        item={item}
        sourceText={record.comment || ""}
        labels={labels}
        review={review}
      />
    );
  };
  return (
    <section className="semantic-review-ledger" aria-label="语义核验清单">
      <header>
        <div>
          <b>语义核验清单</b>
          <span>查看历史原文证据、用户观点及人工调整。</span>
        </div>
        <div className="semantic-review-summary" aria-label="语义覆盖概览">
          <span>
            <CheckCircle size={15} /> 已归类 {displayedSummary.mapped}
          </span>
          <span>无需归类 {displayedSummary.informational}</span>
          <span className={displayedSummary.needsReview ? "has-review" : ""}>
            待判断 {displayedSummary.needsReview}
          </span>
          <span className={displayedSummary.failures ? "has-failure" : ""}>
            系统异常 {displayedSummary.failures}
          </span>
        </div>
      </header>

      {items.length ? (
        <SemanticReviewGroups {...context} renderItem={renderItem} />
      ) : (
        <div className="semantic-review-empty" role="status">
          <WarningCircle size={18} />
          这条历史记录没有已提取的观点，可展开完整原文查看。
        </div>
      )}
    </section>
  );
}
