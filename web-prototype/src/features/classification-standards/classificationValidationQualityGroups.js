/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationItem} ClassificationStandardValidationItem */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunDetail} ClassificationStandardValidationRunDetail */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationValidationSemanticResult} ClassificationValidationSemanticResult */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationValidationUnknownSemantic} ClassificationValidationUnknownSemantic */
/** @typedef {{title: string, note: string, items: ClassificationStandardValidationItem[], informational?: boolean}} QualityGroup */

/** @type {Record<string, string>} */
export const ISSUE_LABELS = {
  duplicate_units: "重复实例",
  extra_labels: "多标实例",
  missing_labels: "漏标实例",
  direction_errors: "方向错误",
  part_errors: "明确部位漏错",
  evidence_errors: "证据检查失败",
  model_errors: "模型调用错误",
  statement_type_errors: "事实状态错误",
  actor_errors: "使用者错配",
  product_errors: "商品对象错配",
  plan_confirmation_errors: "计划或假设误确认为事实",
  event_errors: "事件关系错误",
  condition_errors: "条件遗漏",
  subject_errors: "责任主体错误",
  primary_errors: "主因错误",
};

/** @param {ClassificationStandardValidationItem} item */
function hasBusinessErrors(item) {
  return (
    item.draft.status === "MODEL_ERROR" ||
    Object.keys(ISSUE_LABELS).some(
      (key) => (item.reference_comparison?.draft?.[key] ?? 0) > 0,
    )
  );
}

/** @param {ClassificationStandardValidationItem} item */
function hasVerifiedComparison(item) {
  const comparison = item.reference_comparison?.draft;
  return Boolean(
    !item.reference?.ambiguous &&
    comparison &&
    Object.keys(ISSUE_LABELS).every((key) => comparison[key] === 0),
  );
}

/**
 * @param {ClassificationStandardValidationItem} item
 * @param {ClassificationValidationUnknownSemantic} unknownUnit
 */
function isExpectedUnmapped(item, unknownUnit) {
  if (!hasVerifiedComparison(item)) return false;
  if (typeof unknownUnit === "string") return false;
  return item.draft.extracted_facts?.some((fact) => {
    const evidenceSpans = fact.evidence_spans ?? [];
    const mapping = item.draft.fact_mappings?.find(
      (entry) => entry.fact_id === fact.fact_id,
    );
    return (
      fact.opinion === unknownUnit.opinion &&
      mapping?.label_codes?.length === 0 &&
      (([
        "PREDICTION",
        "HYPOTHESIS",
        "NOT_TESTED",
        "NEGATED",
        "ADVICE",
        "INTENT",
      ].includes(fact.statement_type) &&
        evidenceSpans.length > 0 &&
        evidenceSpans.every((span) => span.text && item.comment.includes(span.text))) ||
        item.reference?.facts?.some((expected) => {
          const expectedEvidence = expected.evidence;
          return (
            expected.label_codes?.length === 0 &&
            expected.expected_statement_type === fact.statement_type &&
            typeof expectedEvidence === "string" &&
            evidenceSpans.some((span) => span.text.includes(expectedEvidence))
          );
        }))
    );
  });
}

/** @param {ClassificationStandardValidationRunDetail} run @returns {QualityGroup[]} */
export function classificationValidationQualityGroups(run) {
  const items = run.items || [];
  const gaps = items.filter((item) =>
    item.draft.unknown_semantics?.some((unit) => !isExpectedUnmapped(item, unit)),
  );
  const attention = items.filter(
    (item) =>
      hasVerifiedComparison(item) &&
      !gaps.includes(item) &&
      ((item.draft.unknown_semantics?.length ?? 0) > 0 ||
        item.draft.review_reasons?.length > 0),
  );
  /** @type {QualityGroup[]} */
  const groups = [
    {
      title: "语义智能体问题",
      note: "参考答案不一致或调用失败。具体归因仍需结合原文检查。",
      items: items.filter(hasBusinessErrors),
    },
    {
      title: "标签体系问题",
      note: "以下是待核对的覆盖缺口，不自动认定为标签缺陷；请检查已有标签定义后决定。",
      items: gaps,
    },
    {
      title: "人工歧义",
      note: "歧义参考答案不计自动评分；其他复核原因由人工确认，不能直接算错误。",
      items: items.filter(
        (item) =>
          !attention.includes(item) &&
          (item.reference?.ambiguous || item.draft.review_reasons?.length > 0),
      ),
    },
    {
      title: "预期留空或人工关注（非阻断）",
      note: "参考已确认留空或尚未确认的预测、否认、建议等事实不直接视为标签覆盖缺口。业务比对未发现错误，相关说明保留供人工阅读；非阻断不代表已完成语义审阅。",
      items: attention,
      informational: true,
    },
  ];

  return groups;
}
