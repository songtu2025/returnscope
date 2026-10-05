const REVIEW_DISPOSITIONS = new Set([
  "ANALYSIS_FAILURE",
  "MODEL_ERROR",
  "MAPPING_UNCERTAIN",
  "TAXONOMY_GAP",
  "TRUE_AMBIGUITY",
  "UNKNOWN",
]);

const INFORMATIONAL_DISPOSITIONS = new Set([
  "EXPECTED_ABSTENTION",
  "NO_TAG_NEEDED",
  "OUT_OF_SCOPE",
]);

/**
 * @typedef {import("../../shared/api/reviewBatchContracts").SemanticItemReview} SemanticItemReview
 * @typedef {import("../../shared/api/reviewBatchContracts").SemanticReviewLedgerItem} SemanticReviewLedgerItem
 */

/** @type {Record<string, string>} */
export const REVIEW_DISPOSITION_LABELS = {
  MAPPED: "已归类",
  EXPECTED_ABSTENTION: "按规则无需归类",
  NO_TAG_NEEDED: "无需归类",
  OUT_OF_SCOPE: "当前范围外",
  TAXONOMY_GAP: "标签体系缺口",
  MAPPING_UNCERTAIN: "标签待判断",
  TRUE_AMBIGUITY: "原文含义不明确",
  ANALYSIS_FAILURE: "系统处理失败",
  MODEL_ERROR: "系统处理失败",
  UNKNOWN: "待判断",
  UNEXPLAINED: "未解释原文片段",
};

/** @param {SemanticReviewLedgerItem} item */
export function priority(item) {
  if (dispositionTone(item.disposition) === "failure") return 0;
  if (item.disposition === "UNEXPLAINED") return 1;
  if (REVIEW_DISPOSITIONS.has(item.disposition)) return 1;
  if (INFORMATIONAL_DISPOSITIONS.has(item.disposition)) return 3;
  return 2;
}

/** @param {string} disposition */
export function dispositionTone(disposition) {
  if (["ANALYSIS_FAILURE", "MODEL_ERROR"].includes(disposition)) {
    return "failure";
  }
  if (disposition === "UNEXPLAINED") return "review";
  if (REVIEW_DISPOSITIONS.has(disposition)) return "review";
  if (INFORMATIONAL_DISPOSITIONS.has(disposition)) return "informational";
  return "mapped";
}

/** @param {SemanticReviewLedgerItem} item @param {string} sourceText */
export function reviewDiagnosticPresentation(item, sourceText) {
  return {
    opinionHeading: item.manual
      ? "人工补充观点"
      : item.evidenceSource === "SYSTEM"
        ? "诊断提示"
        : "提取观点",
    suggestedAction:
      item.businessReviewRequired === true
        ? "请根据原文确认业务观点和标签；缺少证据时从原文补录。"
        : "请联系管理员检查并重新运行。",
    missingEvidence:
      item.businessReviewRequired === true &&
      item.evidenceSource === "SYSTEM" &&
      (!item.evidence ||
        item.evidence === "无文本证据" ||
        !sourceText.includes(item.evidence)),
  };
}

/** @param {SemanticReviewLedgerItem} item @param {SemanticItemReview | null | undefined} review @returns {SemanticReviewLedgerItem} */
export function effectiveReviewItem(item, review) {
  if (
    !review ||
    item.businessReviewRequired === false ||
    dispositionTone(item.disposition) === "failure"
  ) {
    return item;
  }
  if (review.action === "change_label") {
    return {
      ...item,
      labelCode: review.label_code || item.labelCode,
      labelPath: [],
      disposition: "MAPPED",
    };
  }
  if (["no_tag_needed", "remove"].includes(review.action)) {
    return { ...item, labelCode: "", labelPath: [], disposition: "NO_TAG_NEEDED" };
  }
  return item;
}

/** @param {SemanticReviewLedgerItem[]} items @returns {import("../../shared/api/reviewBatchContracts").SemanticReviewSummary} */
export function semanticReviewSummary(items) {
  return {
    mapped: items.filter((item) => item.disposition === "MAPPED").length,
    informational: items.filter((item) =>
      INFORMATIONAL_DISPOSITIONS.has(item.disposition),
    ).length,
    needsReview: items.filter(
      (item) =>
        REVIEW_DISPOSITIONS.has(item.disposition) &&
        dispositionTone(item.disposition) !== "failure",
    ).length,
    failures: items.filter((item) => dispositionTone(item.disposition) === "failure")
      .length,
  };
}
