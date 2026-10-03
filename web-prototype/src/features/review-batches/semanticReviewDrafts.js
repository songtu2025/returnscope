/** @typedef {import("./semanticLedgerContracts").AddedSemanticItem} AddedSemanticItem */
/** @typedef {import("./semanticLedgerContracts").ReviewLabel} ReviewLabel */
/** @typedef {import("./semanticLedgerContracts").SemanticItemReview} SemanticItemReview */
/** @typedef {import("./semanticLedgerContracts").SemanticReviewLedgerItem} SemanticReviewLedgerItem */

/** @type {Record<string, string>} */
export const ACTION_LABELS = {
  change_label: "修改标签",
  remove: "删除错误提取",
  no_tag_needed: "标记为无需归类",
};

/** @type {Record<string, string>} */
export const SENTIMENT_LABELS = { POSITIVE: "正向", NEGATIVE: "负向", NEUTRAL: "中性" };

/** @param {string} code @param {ReviewLabel[]} labels @param {string} [selected] */
export function selectedSentiment(code, labels, selected = "") {
  const allowed = labels.find((label) => label.code === code)?.allowed_sentiments ?? [];
  return selected || (allowed.length === 1 ? allowed[0] : "");
}

/** @param {AddedSemanticItem} item @param {number} index @returns {SemanticReviewLedgerItem} */
export function manualItem(item, index) {
  return {
    id: item.item_id || `manual-${index + 1}`,
    evidence: item.evidence_text,
    evidenceSource: "COMMENT",
    opinion: item.opinion,
    labelCode: item.label_code,
    labelPath: [],
    disposition: "MAPPED",
    reason: item.note || "人工补充的遗漏观点",
    diagnosticDomain: "",
    diagnosticCode: "",
    diagnosticTitle: "",
    detailStatus: "",
    primaryResult: "",
    secondaryResult: "",
    diagnosticDetail: "",
    diagnosticAction: "",
    businessReviewRequired: true,
    manual: true,
    sentiment: item.sentiment || "",
  };
}

/** @param {SemanticItemReview[]} items @param {SemanticItemReview} next */
export function upsert(items, next) {
  const existing = items.findIndex(
    (item) => item.semantic_item_id === next.semantic_item_id,
  );
  if (existing < 0) return [...items, next];
  return items.map((item, index) => (index === existing ? next : item));
}

/** @param {AddedSemanticItem[]} items */
export function nextManualId(items) {
  let index = items.length + 1;
  while (items.some((item) => item.item_id === `manual-${index}`)) index += 1;
  return `manual-${index}`;
}
