/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationItem} ClassificationStandardValidationItem */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunDetail} ClassificationStandardValidationRunDetail */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationValidationSemanticResult} ClassificationValidationSemanticResult */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationValidationUnknownSemantic} ClassificationValidationUnknownSemantic */
/** @typedef {{title: string, note: string, items: ClassificationStandardValidationItem[], informational?: boolean}} QualityGroup */

/** @type {Record<string, string>} */
const ISSUE_LABELS = {
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

/** @param {{run: ClassificationStandardValidationRunDetail}} props */
export function ClassificationValidationQuality({ run }) {
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
  const gate = run.quality_gate;
  const blocking = /** @type {string[]} */ (gate?.blocking || []);
  const warnings = /** @type {string[]} */ (gate?.warnings || []);
  const referenceEvaluation = run.summary?.reference_evaluation;
  return (
    <section className="standard-quality-summary" aria-label="质量门槛与问题分组">
      <h3>质量门槛与问题分组</h3>
      <div
        className={`standard-validation-notice ${gate?.passed === false ? "blocking" : "warning"}`}
        role={gate?.passed === false ? "alert" : "status"}
      >
        <b>
          {gate?.status === "passed"
            ? "自动质量检查通过，仍需人工审阅"
            : gate?.passed === false
              ? "自动质量检查未通过，请人工判断是否发布"
              : "未配置自动质量检查，请人工判断是否发布"}
        </b>
        <p>
          {gate?.note ||
            "自动检查只覆盖人工参考答案；观点与证据是否充分、覆盖缺口及业务歧义仍需人工判断。"}
        </p>
        {blocking.length > 0 && (
          <div>
            <strong>发布风险项</strong>
            <ul>
              {blocking.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        )}
        {warnings.length > 0 && (
          <div>
            <strong>人工复核警告</strong>
            <ul>
              {warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </div>
        )}
        {gate?.policy && (
          <small>
            策略：{gate.policy.version} · 非歧义参考至少{" "}
            {gate.policy.min_reference_samples} 条、覆盖{" "}
            {gate.policy.min_reference_coverage}%；实例匹配至少{" "}
            {gate.policy.min_instance_match_rate}%，重复事实样本不超过{" "}
            {gate.policy.max_duplicate_rate}%。
            {gate.policy.thresholds && (
              <>
                自动检查重点项：
                {Object.entries(gate.policy.thresholds)
                  .filter(([, limit]) => limit === 0)
                  .map(([key]) => ISSUE_LABELS[key] || key)
                  .join("、")}
                ，均须为 0。
              </>
            )}
          </small>
        )}
      </div>
      {referenceEvaluation && (
        <p>
          参考维度覆盖：
          {Object.entries({
            event: "事件",
            condition: "条件",
            subject: "责任主体",
            primary: "主因",
          })
            .map(([key, label]) => {
              const count = referenceEvaluation.scope_sample_counts?.[key] || 0;
              return `${label} ${count ? `${count} 条已评估` : "未评估"}`;
            })
            .join("；")}
          。旧表缺少对应列不能视为该维度零错误。
        </p>
      )}
      <p>各分组按样本计数，可能重叠，不相加计算错误率。</p>
      {groups.map((group) => (
        <details key={group.title} className="standard-quality-group">
          <summary>
            {group.title} · {group.items.length} 条
            {group.informational ? "记录" : "待检查"}
          </summary>
          <p>{group.note}</p>
          {group.items.length === 0 ? (
            <p>当前没有对应信号；不代表该类问题已全部排除。</p>
          ) : (
            group.items.map((item) => (
              <details key={item.classification_key}>
                <summary>
                  来源第 {item.source_row ?? "—"} 行 · {item.comment.slice(0, 70)}
                </summary>
                <p>{item.comment}</p>
                <ul>
                  {Object.entries(ISSUE_LABELS)
                    .filter(
                      ([key]) => (item.reference_comparison?.draft?.[key] ?? 0) > 0,
                    )
                    .map(([key, label]) => (
                      <li key={key}>
                        {label}：{item.reference_comparison?.draft?.[key] ?? 0}
                      </li>
                    ))}
                  {item.draft.review_reasons?.map((reason, index) => (
                    <li key={`review-${index}`}>{reason}</li>
                  ))}
                </ul>
                {(item.draft.unknown_semantics?.length ?? 0) > 0 && (
                  <p>
                    {group.informational ? "留空事实：" : "未覆盖语义："}
                    {(item.draft.unknown_semantics ?? [])
                      .map((unit) =>
                        typeof unit === "string"
                          ? unit
                          : unit.opinion ||
                            unit.evidence ||
                            unit.reason ||
                            "请查看逐条结果",
                      )
                      .join("；")}
                  </p>
                )}
                <ValidationFactTrace result={item.draft} />
              </details>
            ))
          )}
        </details>
      ))}
    </section>
  );
}

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
