const ISSUE_LABELS = {
  duplicate_units: "重复实例",
  extra_labels: "多标实例",
  missing_labels: "漏标实例",
  direction_errors: "方向差异",
  part_errors: "明确部位差异",
  evidence_errors: "证据检查差异",
  model_errors: "模型调用错误",
  statement_type_errors: "事实状态差异",
  actor_errors: "使用者差异",
  product_errors: "商品对象差异",
  plan_confirmation_errors: "计划或假设事实状态差异",
  event_errors: "事件关系差异",
  condition_errors: "条件差异",
  subject_errors: "责任主体差异",
  primary_errors: "主因字段差异",
};

function hasAutomaticCheckDifferences(item) {
  return (
    item.draft.status === "MODEL_ERROR" ||
    Object.keys(ISSUE_LABELS).some((key) => item.reference_comparison?.draft?.[key] > 0)
  );
}

function hasVerifiedComparison(item) {
  const comparison = item.reference_comparison?.draft;
  return (
    !item.reference?.ambiguous &&
    comparison &&
    Object.keys(ISSUE_LABELS).every((key) => comparison[key] === 0)
  );
}

function isExpectedUnmapped(item, unknown) {
  if (!hasVerifiedComparison(item)) return false;
  return item.draft.extracted_facts?.some((fact) => {
    const mapping = item.draft.fact_mappings?.find(
      (entry) => entry.fact_id === fact.fact_id,
    );
    return (
      fact.opinion === unknown.opinion &&
      mapping?.label_codes?.length === 0 &&
      (([
        "PREDICTION",
        "HYPOTHESIS",
        "NOT_TESTED",
        "NEGATED",
        "ADVICE",
        "INTENT",
      ].includes(fact.statement_type) &&
        fact.evidence_spans?.length > 0 &&
        fact.evidence_spans.every(
          (span) => span.text && item.comment.includes(span.text),
        )) ||
        item.reference?.facts?.some(
          (expected) =>
            expected.label_codes?.length === 0 &&
            expected.expected_statement_type === fact.statement_type &&
            expected.evidence &&
            fact.evidence_spans?.some((span) => span.text.includes(expected.evidence)),
        ))
    );
  });
}

const INTEGER_FORMAT = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 0,
});

const DECIMAL_FORMAT = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 2,
});

function formatNumber(value, format = INTEGER_FORMAT) {
  return Number.isFinite(value) ? format.format(value) : "--";
}

function EfficiencyComparison({ efficiency }) {
  const sides = efficiency?.sides || {};
  const rows = ["baseline", "draft"].filter((side) => sides[side]);
  if (rows.length === 0) return null;
  return (
    <section aria-label="执行效率对比">
      <h4>执行效率</h4>
      <table>
        <thead>
          <tr>
            <th>结果</th>
            <th>模型调用</th>
            <th>Token</th>
            <th>覆盖审计</th>
            <th>人工复核</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((side) => {
            const values = sides[side];
            return (
              <tr key={side}>
                <td>{side === "baseline" ? "对照" : "候选"}</td>
                <td>
                  {formatNumber(values.model_calls)} 次 · 平均{" "}
                  {formatNumber(values.average_model_calls, DECIMAL_FORMAT)} 次/条
                </td>
                <td>
                  {formatNumber(values.total_tokens)} · 平均{" "}
                  {formatNumber(values.average_tokens, DECIMAL_FORMAT)} Token/条
                </td>
                <td>
                  {formatNumber(values.coverage_audit_rate, DECIMAL_FORMAT)}% ·{" "}
                  {formatNumber(values.coverage_audit_count)} 次
                </td>
                <td>
                  {formatNumber(values.review_rate, DECIMAL_FORMAT)}% ·{" "}
                  {formatNumber(values.review_count)} 条
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <small>指标来自本次实际执行记录；历史运行未记录的项目显示 --。</small>
    </section>
  );
}

export function ClassificationValidationQuality({ run }) {
  const items = run.items || [];
  const gaps = items.filter((item) =>
    item.draft.unknown_semantics?.some((unit) => !isExpectedUnmapped(item, unit)),
  );
  const attention = items.filter(
    (item) =>
      hasVerifiedComparison(item) &&
      !gaps.includes(item) &&
      (item.draft.unknown_semantics?.length > 0 ||
        item.draft.review_reasons?.length > 0),
  );
  const groups = [
    {
      title: "自动检查差异",
      note: "系统仅展示与参考答案的字段差异或调用失败，不直接替代业务员结论。",
      items: items.filter(hasAutomaticCheckDifferences),
    },
    {
      title: "标签覆盖待核对",
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
      note: "参考已确认留空或尚未确认的预测、否认、建议等事实不直接视为标签覆盖缺口。自动检查未发现差异，相关说明保留供业务员阅读；非阻断不代表已完成语义审阅。",
      items: attention,
      informational: true,
    },
  ];
  const gate = run.quality_gate;
  const blocking = /** @type {string[]} */ (gate?.blocking || []);
  const warnings = /** @type {string[]} */ (gate?.warnings || []);
  const referenceEvaluation = run.summary?.reference_evaluation;
  return (
    <section className="standard-quality-summary" aria-label="质量门槛与自动检查分组">
      <h3>质量门槛与自动检查分组</h3>
      <div
        className={`standard-validation-notice ${gate?.passed === false ? "blocking" : "warning"}`}
        role={gate?.passed === false ? "alert" : "status"}
      >
        <b>
          {gate?.status === "passed"
            ? "自动质量门槛通过，仍需人工审阅"
            : gate?.passed === false
              ? "自动质量门槛未通过，不能确认发布"
              : "未配置自动质量门槛，保留人工确认流程"}
        </b>
        <p>
          {gate?.note ||
            "自动检查只覆盖人工参考答案；观点与证据是否充分、覆盖缺口及业务歧义仍需人工判断。"}
        </p>
        {blocking.length > 0 && (
          <div>
            <strong>发布阻断项</strong>
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
                发布阻断零容忍项：
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
      <EfficiencyComparison efficiency={run.summary?.efficiency} />
      <p>
        自动检查展示标签抽取及相关字段与参考答案的差异，不根据主因或次要标签自动判定正确、部分正确或错误；重要性和最终结论由业务员结合原文判断。
      </p>
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
                    .filter(([key]) => item.reference_comparison?.draft?.[key] > 0)
                    .map(([key, label]) => (
                      <li key={key}>
                        {label}：{item.reference_comparison.draft[key]}
                      </li>
                    ))}
                  {item.draft.review_reasons?.map((reason, index) => (
                    <li key={`review-${index}`}>{reason}</li>
                  ))}
                </ul>
                {item.draft.unknown_semantics?.length > 0 && (
                  <p>
                    {group.informational ? "留空事实：" : "未覆盖语义："}
                    {item.draft.unknown_semantics
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

export function ValidationFactTrace({ result }) {
  if (!result.extracted_facts?.length) return null;
  const mappings = new Map(
    (result.fact_mappings || []).map((mapping) => [mapping.fact_id, mapping]),
  );
  return (
    <details className="standard-fact-trace">
      <summary>事实状态、对象与条件</summary>
      {result.extracted_facts.map((fact) => (
        <p key={fact.fact_id}>
          <b>{fact.statement_type}</b> · 使用者 {fact.actor_ref} · 商品{" "}
          {fact.product_ref} · 事件 {fact.event_ref || "未记录"} · 条件{" "}
          {fact.condition || "未限定"} · 责任主体 {fact.subject || "未记录"} · 主因字段
          {fact.is_primary_reason === true
            ? " 是"
            : fact.is_primary_reason === false
              ? " 否"
              : " 未记录"}
          <br />
          {fact.opinion}
          <br />
          {fact.evidence_spans?.map((span) => span.text).join("；")}
          <br />
          映射记录：
          {mappings.get(fact.fact_id)?.label_codes?.join("、") || "未映射标签"}
          {mappings.get(fact.fact_id)?.reason && (
            <> · {mappings.get(fact.fact_id).reason}</>
          )}
        </p>
      ))}
      <small>映射记录用于追溯；是否计入确认结果，以最终语义观点为准。</small>
    </details>
  );
}
