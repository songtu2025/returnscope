const SENSITIVE_FIELD = /(password|secret|token|api[_-]?key|encryption[_-]?key)/i;

/** @type {Record<string, string>} */
const FIELD_LABELS = {
  status: "状态",
  display_name: "名称",
  name: "名称",
  model_key: "模型 ID",
  supported_efforts: "推理强度",
  active: "启用状态",
  validation_status: "验证状态",
  validation_message: "验证结果",
  message: "结果信息",
  base_url: "服务地址",
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

/** @param {{before?: unknown, after?: unknown, partialAfter?: boolean}} props */
export function AuditDiff({ before, after, partialAfter = false }) {
  const beforeFields = flattenObject(before);
  // 产品行修改的新值是增量；缺省字段沿用旧值，显式空值仍表示清空。
  const afterFields = {
    ...(partialAfter ? beforeFields : {}),
    ...flattenObject(after),
  };
  const keys = Array.from(
    new Set([...Object.keys(beforeFields), ...Object.keys(afterFields)]),
  ).sort();
  const changed = keys.filter(
    (key) => JSON.stringify(beforeFields[key]) !== JSON.stringify(afterFields[key]),
  );
  const unchanged = keys.filter((key) => !changed.includes(key));
  return (
    <div className="audit-diff">
      <h3>字段变化 · {changed.length} 项</h3>
      {changed.length ? (
        <AuditFieldTable
          keys={changed}
          beforeFields={beforeFields}
          afterFields={afterFields}
        />
      ) : (
        <p className="muted-line">本次操作没有字段变化。</p>
      )}
      {unchanged.length > 0 && (
        <details className="audit-unchanged">
          <summary>未变化字段 · {unchanged.length} 项</summary>
          <AuditFieldTable
            keys={unchanged}
            beforeFields={beforeFields}
            afterFields={afterFields}
          />
        </details>
      )}
    </div>
  );
}

/** @param {{keys: string[], beforeFields: Record<string, unknown>, afterFields: Record<string, unknown>}} props */
function AuditFieldTable({ keys, beforeFields, afterFields }) {
  return (
    <table className="audit-diff-table" aria-label="字段差异">
      <thead>
        <tr>
          <th scope="col">字段</th>
          <th scope="col">修改前</th>
          <th scope="col">修改后</th>
        </tr>
      </thead>
      <tbody>
        {keys.map((key) => (
          <tr key={key}>
            <th scope="row" className="audit-field-name">
              {FIELD_LABELS[key] ?? key}
              {FIELD_LABELS[key] && <code>{key}</code>}
            </th>
            <td>{displayAuditValue(key, beforeFields[key])}</td>
            <td>{displayAuditValue(key, afterFields[key])}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** @param {unknown} value @param {string} [prefix] @param {Record<string, unknown>} [result] */
function flattenObject(value, prefix = "", result = {}) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    if (value !== null && value !== undefined) result[prefix || "内容"] = value;
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
  if (Array.isArray(value))
    return value.length ? JSON.stringify(maskAuditValues(value)) : "无";
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

/** @param {unknown} value @returns {unknown} */
function maskAuditValues(value) {
  if (Array.isArray(value)) return value.map(maskAuditValues);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, child]) => [
        key,
        SENSITIVE_FIELD.test(key) ? "••••••" : maskAuditValues(child),
      ]),
    );
  }
  return value;
}
