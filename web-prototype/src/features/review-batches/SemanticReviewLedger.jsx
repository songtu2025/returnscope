import { dispositionTone } from "./semanticReviewPresentation";
import Button from "antd/es/button";
import { CheckCircle, Trash, WarningCircle } from "@phosphor-icons/react";
import { upsert } from "./semanticReviewDrafts";
import { ReviewLedgerItem } from "./SemanticReviewItem";
import { SemanticReviewAddForm } from "./SemanticReviewAddForm";
import { SemanticReviewGroups } from "./SemanticReviewGroups";
import { SemanticReviewControls } from "./SemanticReviewControls";
import { useSemanticLedger } from "./useSemanticLedger";

/** @typedef {import("./semanticLedgerContracts").SemanticReviewLedgerItem} SemanticReviewLedgerItem */

/** @param {import("./semanticLedgerContracts").SemanticLedgerProps} props */
export function SemanticReviewLedger(props) {
  const context = { ...props, ...useSemanticLedger(props) };
  const {
    record,
    labels,
    editable,
    addedItems,
    onItemReviews,
    onAddedItems,
    adding,
    reviews,
    items,
    reviewFor,
    displayedSummary,
  } = context;

  /** @param {SemanticReviewLedgerItem} item */
  const renderItem = (item) => {
    const review = reviewFor(item);
    return (
      <ReviewLedgerItem
        key={item.id}
        item={item}
        sourceText={record.comment || ""}
        labels={labels}
        editable={
          editable &&
          dispositionTone(item.disposition) !== "failure" &&
          item.businessReviewRequired !== false
        }
        review={review}
        onReview={(next) => onItemReviews(upsert(reviews, next))}
        onReset={() =>
          onItemReviews(
            reviews.filter((candidate) => candidate.semantic_item_id !== item.id),
          )
        }
      />
    );
  };
  return (
    <section className="semantic-review-ledger" aria-label="语义核验清单">
      <header>
        <div>
          <b>语义核验清单</b>
          <span>按“原文证据—用户观点—标签或处置”核验，无需逐标签确认。</span>
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
          当前结果没有可核验的观点，请展开完整原文判断是否需要补充。
        </div>
      )}

      {editable && <SemanticReviewControls {...context} />}

      {editable && adding && <SemanticReviewAddForm {...context} />}

      {editable && addedItems.length > 0 && (
        <div className="semantic-review-added-actions">
          <span>已人工补充 {addedItems.length} 项</span>
          <Button
            type="text"
            size="small"
            icon={<Trash size={15} />}
            onClick={() => onAddedItems(addedItems.slice(0, -1))}
          >
            移除最后一项
          </Button>
        </div>
      )}
    </section>
  );
}
