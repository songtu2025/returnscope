/** @typedef {"confirm" | "modify" | "exclude"} ReviewAction */
/** @typedef {{labelCorrectness: string, evidenceCompleteness: string, reviewRouting: string}} ReviewAssessment */
/** @typedef {{key: string, storedKey: string, label: string, options: Array<[string, string]>}} AssessmentField */

/** @type {AssessmentField[]} */
export const REVIEW_ASSESSMENT_FIELDS = [
  {
    key: "labelCorrectness",
    storedKey: "label_correctness",
    label: "标签正确性",
    options: [
      ["correct", "正确"],
      ["partial", "部分正确"],
      ["incorrect", "错误"],
      ["not_applicable", "不适用"],
    ],
  },
  {
    key: "evidenceCompleteness",
    storedKey: "evidence_completeness",
    label: "证据完整性",
    options: [
      ["complete", "完整"],
      ["partial", "部分完整"],
      ["missing", "缺失"],
    ],
  },
  {
    key: "reviewRouting",
    storedKey: "review_routing",
    label: "路由合理性",
    options: [
      ["correct", "路由正确"],
      ["should_auto_approve", "本应自动通过"],
      ["should_manual_review", "本应人工复核"],
    ],
  },
];

/** @type {Record<ReviewAction, ReviewAssessment>} */
const DEFAULTS = {
  confirm: {
    labelCorrectness: "correct",
    evidenceCompleteness: "complete",
    reviewRouting: "correct",
  },
  modify: {
    labelCorrectness: "partial",
    evidenceCompleteness: "partial",
    reviewRouting: "should_manual_review",
  },
  exclude: {
    labelCorrectness: "not_applicable",
    evidenceCompleteness: "missing",
    reviewRouting: "correct",
  },
};

/** @param {ReviewAction} action @returns {ReviewAssessment} */
export function defaultReviewAssessment(action) {
  return { ...DEFAULTS[action] };
}

/** @param {Record<string, any>} record @param {ReviewAction} [action] */
export function reviewAssessment(record, action = "confirm") {
  const stored =
    record?.classification?.human_review_assessment ??
    record?.human_review_assessment ??
    {};
  const defaults = defaultReviewAssessment(action);
  return {
    labelCorrectness: stored.label_correctness || defaults.labelCorrectness,
    evidenceCompleteness: stored.evidence_completeness || defaults.evidenceCompleteness,
    reviewRouting: stored.review_routing || defaults.reviewRouting,
  };
}

/** @param {AssessmentField} field @param {string} value */
export function reviewAssessmentLabel(field, value) {
  return field.options.find(([code]) => code === value)?.[1] || "未单独记录";
}
