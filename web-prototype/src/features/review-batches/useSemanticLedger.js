import { useMemo, useState } from "react";
import {
  dispositionTone,
  effectiveReviewItem,
  semanticReviewLedger,
} from "./semanticReviewPresentation";
import { selectedSentiment, manualItem, nextManualId } from "./semanticReviewDrafts";

/** @typedef {import("./semanticLedgerContracts").SemanticReviewLedgerItem} SemanticReviewLedgerItem */

/** @param {import("./semanticLedgerContracts").SemanticLedgerProps} props */
export function useSemanticLedger({
  record,
  labels,
  editable,
  itemReviews,
  addedItems,
  coverageStatus,
  onAddedItems,
}) {
  const ledger = useMemo(() => semanticReviewLedger(record), [record]);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({
    evidence_text: "",
    opinion: "",
    label_code: "",
    sentiment: "",
  });
  const reviews = itemReviews ?? [];
  const manualItems = (addedItems ?? []).map(manualItem);
  const items = [
    ...ledger.items.filter((item) => !item.manual || item.applied),
    ...manualItems,
  ];
  const systemItems = items.filter((item) =>
    ["ANALYSIS_FAILURE", "MODEL_ERROR"].includes(item.disposition),
  );
  const businessItems = items.filter(
    (item) => !["ANALYSIS_FAILURE", "MODEL_ERROR"].includes(item.disposition),
  );
  /** @param {SemanticReviewLedgerItem} item */
  const reviewFor = (item) =>
    reviews.find((candidate) => candidate.semantic_item_id === item.id) ??
    (!editable ? (item.review ?? undefined) : undefined);
  const summary = items.reduce(
    (counts, item) => {
      const review = reviewFor(item);
      const effective = effectiveReviewItem(item, review);
      const tone = dispositionTone(effective.disposition);
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

  const addItem = () => {
    const next = {
      item_id: nextManualId(addedItems),
      evidence_text: draft.evidence_text.trim(),
      opinion: draft.opinion.trim(),
      label_code: draft.label_code,
      note: "人工补充的遗漏观点",
      sentiment: selectedSentiment(draft.label_code, labels, draft.sentiment),
    };
    onAddedItems([...addedItems, next]);
    setDraft({ evidence_text: "", opinion: "", label_code: "", sentiment: "" });
    setAdding(false);
  };
  return {
    adding,
    setAdding,
    draft,
    setDraft,
    reviews,
    items,
    systemItems,
    businessItems,
    reviewFor,
    displayedSummary,
    addItem,
  };
}
