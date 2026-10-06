/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationItem} ClassificationStandardValidationItem */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunDetail} ClassificationStandardValidationRunDetail */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationValidationSemanticResult} ClassificationValidationSemanticResult */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationValidationUnknownSemantic} ClassificationValidationUnknownSemantic */
/** @param {{result: ClassificationValidationSemanticResult}} props */
export function ValidationFactTrace({ result }) {
  if (!result.extracted_facts?.length) return null;
  const mappings = new Map(
    (result.fact_mappings || []).map((mapping) => [mapping.fact_id, mapping]),
  );
  return (
    <details className="standard-fact-trace">
      <summary>事实状态、对象与条件</summary>
      {result.extracted_facts.map((fact) => {
        const mapping = mappings.get(fact.fact_id);
        return (
          <p key={fact.fact_id}>
            <b>{fact.statement_type}</b> · 使用者 {fact.actor_ref} · 商品{" "}
            {fact.product_ref} · 事件 {fact.event_ref || "未记录"} · 条件{" "}
            {fact.condition || "未限定"} · 责任主体 {fact.subject || "未记录"} ·{" "}
            {fact.is_primary_reason === true ? (
              <strong>主因</strong>
            ) : (
              <span>{fact.is_primary_reason === false ? "非主因" : "主因未记录"}</span>
            )}
            <br />
            {fact.opinion}
            <br />
            {fact.evidence_spans?.map((span) => span.text).join("；")}
            <br />
            映射记录：
            {mapping?.label_codes?.join("、") || "未映射标签"}
            {mapping?.reason && <> · {mapping.reason}</>}
          </p>
        );
      })}
      <small>映射记录用于追溯；是否计入确认结果，以最终语义观点为准。</small>
    </details>
  );
}
