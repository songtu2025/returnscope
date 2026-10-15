import { selectedSentiment } from "../review-batches/semanticReviewDrafts";

/** @typedef {import("../review-batches/semanticLedgerContracts").ReviewLabel} ReviewLabel */
/** @typedef {{item_id: string, evidence_text: string, opinion: string, label_code: string, sentiment: string}} Draft */
/** @param {Draft[]} items @param {Draft[]} baseline */
export function semanticDraftChanged(items, baseline) {
  return (
    items.length !== baseline.length ||
    items.some((item, index) =>
      /** @type {Array<keyof Draft>} */ ([
        "evidence_text",
        "opinion",
        "label_code",
        "sentiment",
      ]).some((field) => item[field] !== baseline[index]?.[field]),
    )
  );
}
/** @param {Draft} item @param {ReviewLabel[]} labels */
export function semanticItemErrors(item, labels) {
  return {
    evidence_text: item.evidence_text.trim() ? "" : "请填写支持观点的原文证据",
    opinion: item.opinion.trim() ? "" : "请填写用户观点",
    label_code: labels.some((label) => label.code === item.label_code)
      ? ""
      : "请选择有效的归类标签",
    sentiment: selectedSentiment(item.label_code, labels, item.sentiment)
      ? ""
      : "请确定评价方向",
  };
}
