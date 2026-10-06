/** @typedef {import("./ClassificationStandardValidationResult").ClassificationStandardValidationResultProps} ResultProps */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunDetail} ClassificationStandardValidationRunDetail */
/** @typedef {{summary: ClassificationStandardValidationRunDetail["summary"], isNew: boolean, hasChangeBreakdown: boolean}} MetricsProps */
/** @param {{label: string, value: string | number, note: string}} props */
function Metric({ label, value, note }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

/** @param {MetricsProps} props */
function HeadlineMetric({ summary, isNew, hasChangeBreakdown }) {
  return (
    <Metric
      label={isNew ? "有效样本" : hasChangeBreakdown ? "语义变化" : "结果变化"}
      value={
        isNew
          ? summary.sample_size
          : `${hasChangeBreakdown ? summary.semantic_changed_rate : summary.changed_rate}%`
      }
      note={
        isNew
          ? "条真实评论"
          : `${hasChangeBreakdown ? summary.semantic_changed_count : summary.changed_count} 条`
      }
    />
  );
}
/** @param {MetricsProps} props */
export function ValidationMetrics({ summary, isNew, hasChangeBreakdown }) {
  return (
    <div className="standard-validation-metrics">
      <HeadlineMetric
        summary={summary}
        isNew={isNew}
        hasChangeBreakdown={hasChangeBreakdown}
      />
      {!isNew && hasChangeBreakdown && (
        <Metric
          label="主因变化"
          value={`${summary.primary_changed_rate}%`}
          note={`${summary.primary_changed_count} 条`}
        />
      )}
      <Metric
        label="标签覆盖"
        value={`${summary.coverage_rate}%`}
        note={`${summary.coverage_count} 条`}
      />
      <Metric
        label="待审核"
        value={`${summary.review_rate}%`}
        note={`${summary.review_count} 条`}
      />
      <Metric
        label="未知语义"
        value={`${summary.unknown_rate}%`}
        note={`${summary.unknown_count} 条`}
      />
      <Metric
        label="模型错误"
        value={`${summary.error_rate}%`}
        note={`${summary.error_count} 条`}
      />
    </div>
  );
}
