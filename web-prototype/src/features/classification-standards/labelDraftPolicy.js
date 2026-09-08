export function sameLabel(left, right) {
  if (!left || !right) return left === right;
  return [
    "code",
    "name",
    "group",
    "description",
    "keywords",
    "exclusions",
    "examples",
    "allowed_sentiments",
    "allowed_claim_ids",
  ].every(
    (field) => JSON.stringify(left[field] ?? []) === JSON.stringify(right[field] ?? []),
  );
}

export function labelChanges(labels, baseLabels = []) {
  const original = new Map(baseLabels.map((label) => [label.code, label]));
  const codes = new Set(labels.map((label) => label.code));
  return [
    ...labels.map((label, index) => ({
      label,
      index,
      before: original.get(label.code),
      status: !original.has(label.code)
        ? "新增"
        : sameLabel(label, original.get(label.code))
          ? "未修改"
          : "已修改",
    })),
    ...baseLabels
      .filter((label) => !codes.has(label.code))
      .map((label) => ({ label, before: label, index: -1, status: "拟停用" })),
  ];
}

export function reconcileLabelRules(rules = {}, labels, baseRules = {}, restoredCode) {
  const codes = new Set(labels.map((label) => label.code));
  const result = structuredClone(rules);
  const unique = (values) => [
    ...new Map(values.map((value) => [JSON.stringify(value), value])).values(),
  ];
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
  for (const field of [
    "conflicting_label_sets",
    "evidence_requirements",
    "implicit_evidence_rules",
    "claim_evidence_requirements",
  ]) {
    if (!rules[field] && !baseRules[field]) continue;
    const restored = restoredCode
      ? (baseRules[field] ?? []).filter((rule) =>
          Array.isArray(rule)
            ? rule.includes(restoredCode)
            : rule.label_code === restoredCode,
        )
      : [];
    const values = unique([...(rules[field] ?? []), ...restored]);
    result[field] =
      field === "conflicting_label_sets"
        ? values
            .map((group) => group.filter((code) => codes.has(code)))
            .filter((group) => new Set(group).size >= 2)
        : values.filter((rule) => codes.has(rule.label_code));
  }
  for (const field of ["neutral_reason_labels", "required_review_labels"]) {
    if (!rules[field] && !baseRules[field]) continue;
    const restored =
      restoredCode && baseRules[field]?.includes(restoredCode) ? [restoredCode] : [];
    result[field] = [...new Set([...(rules[field] ?? []), ...restored])].filter(
      (code) => codes.has(code),
    );
  }
  return result;
}
