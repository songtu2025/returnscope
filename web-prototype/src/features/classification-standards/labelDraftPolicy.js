/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableLabel} ClassificationStandardEditableLabel */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRules} ClassificationStandardValidationRules */
/** @typedef {"新增" | "未修改" | "已修改" | "拟停用"} ClassificationLabelChangeStatus */
/**
 * @template T
 * @typedef {{label: T, index: number, before?: T, status: ClassificationLabelChangeStatus}} ClassificationLabelChange
 */

/** @type {(keyof ClassificationStandardEditableLabel)[]} */
const LABEL_FIELDS = [
  "code",
  "name",
  "group",
  "parent_code",
  "description",
  "keywords",
  "exclusions",
  "examples",
  "allowed_sentiments",
  "allowed_claim_ids",
];

/**
 * @param {ClassificationStandardEditableLabel | undefined} left
 * @param {ClassificationStandardEditableLabel | undefined} right
 */
export function sameLabel(left, right) {
  if (!left || !right) return left === right;
  return LABEL_FIELDS.every(
    (field) => JSON.stringify(left[field] ?? []) === JSON.stringify(right[field] ?? []),
  );
}

/**
 * @template T
 * @param {(T & ClassificationStandardEditableLabel)[]} labels
 * @param {(T & ClassificationStandardEditableLabel)[]} baseLabels
 * @returns {ClassificationLabelChange<T & ClassificationStandardEditableLabel>[]}
 */
export function labelChanges(labels, baseLabels = []) {
  const original = new Map(baseLabels.map((label) => [label.code, label]));
  const codes = new Set(labels.map((label) => label.code));
  return [
    ...labels.map((label, index) => {
      /** @type {ClassificationLabelChangeStatus} */
      const status = !original.has(label.code)
        ? "新增"
        : sameLabel(label, original.get(label.code))
          ? "未修改"
          : "已修改";
      return { label, index, before: original.get(label.code), status };
    }),
    ...baseLabels
      .filter((label) => !codes.has(label.code))
      .map((label) => {
        /** @type {ClassificationLabelChange<T & ClassificationStandardEditableLabel>} */
        const change = { label, before: label, index: -1, status: "拟停用" };
        return change;
      }),
  ];
}

/**
 * @template T
 * @param {T[]} values
 * @returns {T[]}
 */
function unique(values) {
  return [...new Map(values.map((value) => [JSON.stringify(value), value])).values()];
}

/** @template {{label_code: string}} T @param {T[]} current @param {T[]} base @param {string | undefined} restoredCode @param {Set<string>} codes */
function reconcileLabelRuleList(current, base, restoredCode, codes) {
  const restored = restoredCode
    ? base.filter((rule) => rule.label_code === restoredCode)
    : [];
  return unique([...current, ...restored]).filter((rule) => codes.has(rule.label_code));
}

/**
 * @param {ClassificationStandardValidationRules} rules
 * @param {ClassificationStandardEditableLabel[]} labels
 * @param {ClassificationStandardValidationRules} baseRules
 * @param {string | undefined} restoredCode
 * @returns {ClassificationStandardValidationRules}
 */
export function reconcileLabelRules(rules = {}, labels, baseRules = {}, restoredCode) {
  const codes = new Set(labels.map((label) => label.code));
  const result = structuredClone(rules);
  if (rules.opposite_reason_labels || restoredCode) {
    const entries = { ...rules.opposite_reason_labels };
    if (restoredCode)
      for (const [reason, values] of Object.entries(
        baseRules.opposite_reason_labels ?? {},
      )) {
        if (values.includes(restoredCode))
          entries[reason] = [...new Set([...(entries[reason] ?? []), ...values])];
      }
    result.opposite_reason_labels = Object.fromEntries(
      Object.entries(entries).map(([reason, values]) => [
        reason,
        values.filter((code) => codes.has(code)),
      ]),
    );
  }
  if (rules.conflicting_label_sets || baseRules.conflicting_label_sets) {
    const restored = restoredCode
      ? (baseRules.conflicting_label_sets ?? []).filter((group) =>
          group.includes(restoredCode),
        )
      : [];
    result.conflicting_label_sets = unique([
      ...(rules.conflicting_label_sets ?? []),
      ...restored,
    ])
      .map((group) => group.filter((code) => codes.has(code)))
      .filter((group) => new Set(group).size >= 2);
  }
  if (rules.evidence_requirements || baseRules.evidence_requirements) {
    result.evidence_requirements = reconcileLabelRuleList(
      rules.evidence_requirements ?? [],
      baseRules.evidence_requirements ?? [],
      restoredCode,
      codes,
    );
  }
  if (rules.implicit_evidence_rules || baseRules.implicit_evidence_rules) {
    result.implicit_evidence_rules = reconcileLabelRuleList(
      rules.implicit_evidence_rules ?? [],
      baseRules.implicit_evidence_rules ?? [],
      restoredCode,
      codes,
    );
  }
  if (rules.claim_evidence_requirements || baseRules.claim_evidence_requirements) {
    result.claim_evidence_requirements = reconcileLabelRuleList(
      rules.claim_evidence_requirements ?? [],
      baseRules.claim_evidence_requirements ?? [],
      restoredCode,
      codes,
    );
  }
  /** @type {("neutral_reason_labels" | "required_review_labels")[]} */
  const codeFields = ["neutral_reason_labels", "required_review_labels"];
  for (const field of codeFields) {
    if (!rules[field] && !baseRules[field]) continue;
    const restored =
      restoredCode && baseRules[field]?.includes(restoredCode) ? [restoredCode] : [];
    result[field] = [...new Set([...(rules[field] ?? []), ...restored])].filter(
      (code) => codes.has(code),
    );
  }
  return result;
}
