import { ISSUE_LABELS } from "./classificationValidationQualityGroups";
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunDetail} ClassificationStandardValidationRunDetail */
/** @param {{title: string, messages: string[]}} props */
function QualityGateMessages({ title, messages }) {
  return (
    messages.length > 0 && (
      <div>
        <strong>{title}</strong>
        <ul>
          {messages.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      </div>
    )
  );
}
/** @param {{gate: ClassificationStandardValidationRunDetail["quality_gate"]}} props */
function QualityGatePolicy({ gate }) {
  return (
    gate?.policy && (
      <small>
        策略：{gate.policy.version} · 非歧义参考至少 {gate.policy.min_reference_samples}{" "}
        条、覆盖 {gate.policy.min_reference_coverage}%；实例匹配至少{" "}
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
    )
  );
}
/** @param {{run: ClassificationStandardValidationRunDetail}} props */
function ReferenceDimensionCoverage({ run }) {
  const referenceEvaluation = run.summary?.reference_evaluation;
  return (
    referenceEvaluation && (
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
    )
  );
}
/** @param {{run: ClassificationStandardValidationRunDetail}} props */
export function ValidationQualityGate({ run }) {
  const gate = run.quality_gate;
  const blocking = /** @type {string[]} */ (gate?.blocking || []);
  const warnings = /** @type {string[]} */ (gate?.warnings || []);
  return (
    <>
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

        <QualityGateMessages title="发布风险项" messages={blocking} />
        <QualityGateMessages title="人工复核警告" messages={warnings} />
        <QualityGatePolicy gate={gate} />
      </div>
      <ReferenceDimensionCoverage run={run} />
    </>
  );
}
