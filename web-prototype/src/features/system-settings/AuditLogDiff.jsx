const SENSITIVE_FIELD = /(password|secret|token|api[_-]?key|encryption[_-]?key)/i;

/** @type {Record<string, string>} */
const FIELD_LABELS = {
  status: "状态",
  revision: "修订版本",
  reason: "原因",
  note: "备注",
  actor: "操作人",
  preview_hash: "预检哈希",
  plan_hash: "执行计划哈希",
  result_publish_status: "结果发布状态",
  segment_id: "Listing 片段 ID",
  max_parallel_segments: "Listing 并行数",
  execution_order: "执行顺序",
};

/** @param {{before?: unknown, after?: unknown}} props */
export function AuditDiff({ before, after }) {
  const beforeFields = flattenObject(before);
  const afterFields = flattenObject(after);
  const keys = Array.from(
    new Set([...Object.keys(beforeFields), ...Object.keys(afterFields)]),
  ).sort();
  if (!keys.length) return <p className="muted-line">本次操作没有字段差异明细。</p>;
  return (
    <details className="audit-diff">
      <summary>查看字段差异</summary>
      <div className="audit-diff-table">
        <div className="table-head">
          <span>字段</span>
          <span>修改前</span>
          <span>修改后</span>
        </div>
        {keys.map((key) => (
          <div key={key}>
            <span className="audit-field-name">
              <b>{FIELD_LABELS[key] ?? key}</b>
              {FIELD_LABELS[key] && <code>{key}</code>}
            </span>
            <span>{displayAuditValue(key, beforeFields[key])}</span>
            <span>{displayAuditValue(key, afterFields[key])}</span>
          </div>
        ))}
      </div>
    </details>
  );
}

/** @param {unknown} value @param {string} [prefix] @param {Record<string, unknown>} [result] */
function flattenObject(value, prefix = "", result = {}) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    if (prefix) result[prefix] = value;
    return result;
  }
  Object.entries(value).forEach(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (child && typeof child === "object" && !Array.isArray(child)) {
      flattenObject(child, path, result);
    } else {
      result[path] = child;
    }
  });
  return result;
}

/** @param {string} field @param {unknown} value */
function displayAuditValue(field, value) {
  if (SENSITIVE_FIELD.test(field)) return "••••••";
  if (value === null || value === undefined || value === "") return "未提供";
  if (Array.isArray(value)) return value.length ? value.join("、") : "无";
  return String(value);
}
