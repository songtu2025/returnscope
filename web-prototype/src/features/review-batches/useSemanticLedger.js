import { useMemo } from "react";
import {
  dispositionTone,
  effectiveReviewItem,
  semanticReviewLedger,
} from "./semanticReviewPresentation";
import { manualItem } from "./semanticReviewDrafts";

/** @typedef {import("./semanticLedgerContracts").SemanticReviewLedgerItem} SemanticReviewLedgerItem */

/** @param {import("./semanticLedgerContracts").SemanticLedgerProps} props */
export function useSemanticLedger({ record, itemReviews, addedItems, coverageStatus }) {
  const ledger = useMemo(() => semanticReviewLedger(record), [record]);
  const reviews = itemReviews ?? [];
  const manualItems = (addedItems ?? []).map(manualItem);
  const items = [
    ...ledger.items.filter((item) => !item.manual || item.applied),
    ...manualItems,
  ];
  const systemItems = items.filter((item) =>
    ["failure", "notice"].includes(dispositionTone(item.disposition)),
  );
  const businessItems = items.filter(
    (item) => !["failure", "notice"].includes(dispositionTone(item.disposition)),
  );
  /** @param {SemanticReviewLedgerItem} item */
  const reviewFor = (item) =>
    reviews.find((candidate) => candidate.semantic_item_id === item.id) ??
    item.review ??
    undefined;
  const summary = items.reduce(
    (counts, item) => {
      const review = reviewFor(item);
      const effective = effectiveReviewItem(item, review);
      const tone = dispositionTone(effective.disposition);
      if (tone === "notice") return counts;
      if (tone === "failure") counts.failures += 1;
      else if (tone === "review") counts.needsReview += 1;
      else if (tone === "informational") counts.informational += 1;
      else counts.mapped += 1;
      return counts;
    },
    { mapped: 0, informational: 0, needsReview: 0, failures: 0 },
  );
  const hasHumanAdjustments =
    reviews.length > 0 ||
    manualItems.length > 0 ||
    coverageStatus !== ledger.coverageStatus;
  const displayedSummary =
    !hasHumanAdjustments && ledger.suppliedSummary ? ledger.suppliedSummary : summary;

  return {
    reviews,
    items,
    systemItems,
    businessItems,
    reviewFor,
    displayedSummary,
  };
}
