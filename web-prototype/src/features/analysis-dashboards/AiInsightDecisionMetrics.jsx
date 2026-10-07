import { number, percentage, percentagePoints } from "./decisionReportPresentation";
/** @typedef {import("./analysisDashboardContracts").ReportIssueMetrics} ReportIssueMetrics */
/** @typedef {ReturnType<typeof import("./analysisContextPresentation").analysisContextTerms>} AnalysisContextTerms */

/** @param {{label: string, value: string, note: string, tone?: string}} props */
function MetricCard({ label, value, note, tone = "neutral" }) {
  return (
    <div className={`ai-decision-metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

/** @param {{metrics: ReportIssueMetrics, terms: AnalysisContextTerms}} props */
export function DecisionMetrics({ metrics, terms }) {
  return (
    <div className="ai-decision-metrics">
      <MetricCard
        label={terms.sampleShareLabel}
        value={percentage(metrics.return_sample_share)}
        note={`${number(metrics.matched_return_samples)} / ${number(
          metrics.scoped_return_samples,
        )} 条命中`}
      />
      <MetricCard
        label="高于同口径基线"
        value={percentagePoints(metrics.gap_percentage_points)}
        note={
          metrics.baseline_return_sample_share === null ||
          metrics.baseline_return_sample_share === undefined
            ? "当前没有可用基线"
            : `整体基线 ${percentage(metrics.baseline_return_sample_share)}`
        }
        tone="risk"
      />
      <MetricCard
        label="近期变化"
        value={percentagePoints(metrics.recent_change_percentage_points)}
        note={
          metrics.trend_direction === "insufficient"
            ? "趋势样本不足"
            : `趋势 ${metrics.trend_direction}`
        }
        tone={number(metrics.recent_change_percentage_points) > 0 ? "risk" : "neutral"}
      />
    </div>
  );
}
