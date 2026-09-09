import { useEffect, useRef } from "react";

const RULE_NAMES = {
  neutral_reason_labels: "中性退货原因",
  required_review_labels: "强制人工复核",
  conflicting_label_sets: "标签冲突组合",
  opposite_reason_labels: "相反退货原因",
  evidence_requirements: "证据要求",
  implicit_evidence_rules: "隐含证据规则",
  claim_evidence_requirements: "承诺证据要求",
};

export function ClassificationRuleIssues({
  content,
  onChange,
  focusRequest,
  disabled,
}) {
  const headingRef = useRef(null);
  useEffect(() => {
    if (focusRequest?.kind === "invalid_rule") headingRef.current?.focus();
  }, [focusRequest]);
  const rules = content.validation_rules ?? {};
  const codes = new Set(content.labels.map((label) => label.code));
  const invalidRows = Object.entries(RULE_NAMES).flatMap(([field, name]) => {
    const entries =
      field === "opposite_reason_labels"
        ? Object.entries(rules[field] ?? {})
        : (rules[field] ?? []).map((value, index) => [index, value]);
    return entries.flatMap(([key, value]) => {
      const references = Array.isArray(value)
        ? value
        : typeof value === "string"
          ? [value]
          : [value.label_code];
      const missing = references.filter((code) => !codes.has(code));
      return missing.length ? [{ field, name, key, value, missing }] : [];
    });
  });
  return (
    <section className="standard-detail-section standard-structure-issues">
      <h2 ref={headingRef} tabIndex={-1}>
        标签校验规则
      </h2>
      {invalidRows.length > 0 && (
        <p>
          以下规则引用了当前草稿中不存在的标签。删除会移除该条规则，保存草稿后生效；需要保留的规则请先核对业务含义，通过
          JSON 数据交换重新映射。
        </p>
      )}
      {invalidRows.length ? (
        <ul>
          {invalidRows.map((row) => (
            <li key={`${row.field}-${row.key}`}>
              <div>
                <strong>
                  {row.name}
                  {typeof row.key === "string" ? ` · ${row.key}` : ""}
                </strong>
                <span>未知标签：{row.missing.join("、")}</span>
                <small>完整引用：{JSON.stringify(row.value)}</small>
              </div>
              <button
                type="button"
                className="secondary-button compact-button"
                disabled={disabled}
                onClick={() => {
                  const next =
                    row.field === "opposite_reason_labels"
                      ? Object.fromEntries(
                          Object.entries(rules[row.field]).filter(
                            ([key]) => key !== row.key,
                          ),
                        )
                      : rules[row.field].filter((_, index) => index !== row.key);
                  onChange({
                    ...content,
                    validation_rules: { ...rules, [row.field]: next },
                  });
                }}
                aria-label={`删除${row.name}规则 ${row.missing.join("、")}`}
              >
                删除此条规则
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p>没有引用失效标签的规则。单个标签的统计与复核规则可在标签编辑中调整。</p>
      )}
    </section>
  );
}
