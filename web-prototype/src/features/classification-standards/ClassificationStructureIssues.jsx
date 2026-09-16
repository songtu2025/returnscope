import { taxonomyPath } from "../../lib/taxonomyPresentation";

const ISSUE_TITLES = {
  missing_boundary: "标签判定边界不完整",
  missing_sentiment: "评价方向待确认",
  missing_field: "必填信息不完整",
  invalid_rule: "校验规则需调整",
  invalid_structure: "标签结构需调整",
};

export function ClassificationStructureIssues({ validation, content, onFix, busy }) {
  const issues = validation.issues?.length
    ? validation.issues
    : validation.blocking.map((message) => ({ kind: "invalid_structure", message }));
  const groups = Map.groupBy(issues, (issue) => issue.kind);
  return (
    <section className="standard-structure-issues" aria-label="结构检查">
      <h3>结构检查 · {issues.length} 项待处理</h3>
      <p>逐项修正后保存草稿，系统会重新检查；通过后即可运行样本验证。</p>
      {[...groups].map(([kind, rows]) => (
        <details key={kind} open={rows.length <= 5}>
          <summary>
            {ISSUE_TITLES[kind] || "其他问题"} · {rows.length} 项
          </summary>
          <ul>
            {rows.map((issue, index) => {
              const label = issue.label_code
                ? content.labels.find((item) => item.code === issue.label_code)
                : content.labels[issue.label_index];
              const path = label ? taxonomyPath(content, label).join(" → ") : "";
              const canFix = Boolean(
                label || issue.field || issue.kind === "invalid_rule",
              );
              return (
                <li key={`${issue.label_code || kind}-${index}`}>
                  <div>
                    {path && <strong>{path}</strong>}
                    <span>{issue.message}</span>
                  </div>
                  {canFix && (
                    <button
                      type="button"
                      className="secondary-button compact-button"
                      disabled={busy}
                      onClick={() => onFix(issue)}
                      aria-label={`去修正 ${path || issue.message}`}
                    >
                      去修正
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </details>
      ))}
    </section>
  );
}
