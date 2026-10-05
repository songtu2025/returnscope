import {
  normalizeItem,
  suppliedItems,
  unexplainedItems,
  suppliedSummary,
  derivedItems,
  legacyLabelItems,
  reviewedLedgerItems,
} from "./semanticReviewSources";
import { priority, semanticReviewSummary } from "./semanticReviewPolicy";

export {
  dispositionTone,
  effectiveReviewItem,
  reviewDiagnosticPresentation,
  REVIEW_DISPOSITION_LABELS,
} from "./semanticReviewPolicy";

/**
 * @typedef {import("../../shared/api/reviewBatchContracts").ReviewRecord} ReviewRecord
 * @typedef {import("../../shared/api/reviewBatchContracts").SemanticReviewLedgerData} SemanticReviewLedgerData
 */

/** @param {ReviewRecord} record 将新旧语义结果统一为证据—观点—标签核验清单。 @returns {SemanticReviewLedgerData} */
export function semanticReviewLedger(record) {
  const classification = record?.classification ?? {};
  const supplied = suppliedItems(record);
  let items = Array.isArray(supplied)
    ? supplied.map((item, index) => normalizeItem(item, index))
    : derivedItems(record);
  if (!items.length) items = legacyLabelItems(record);
  items = [...items, ...unexplainedItems(record, items.length)];

  const reviewedItems = reviewedLedgerItems(items, classification);
  const added = (classification.human_added_semantic_items ?? [])
    .filter((item) => !item.applied)
    .map((item, index) => ({
      ...normalizeItem({ ...item, manual: true }, items.length + index, "MAPPED"),
      review: null,
    }));
  const sorted = [...reviewedItems, ...added].sort(
    (left, right) => priority(left) - priority(right),
  );

  return {
    items: sorted,
    summary: semanticReviewSummary(sorted),
    coverageStatus: classification.coverage_review?.status || "complete",
    suppliedSummary: sorted.some(
      (item) => typeof item.businessReviewRequired === "boolean",
    )
      ? null
      : suppliedSummary(record),
  };
}
