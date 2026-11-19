import { percentage, percentagePoints } from "./decisionReportPresentation";
/** @typedef {import("./analysisDashboardContracts").SemanticInsightKind} SemanticInsightKind */

export const insightKindLabels = /** @type {Record<SemanticInsightKind, string>} */ ({
  risk: "风险",
  polarization: "分化与冲突",
  opportunity: "优势机会",
  data_gap: "数据缺口",
});

const integer = new Intl.NumberFormat("zh-CN");

/** @param {number | undefined} value */
export function feedbackCount(value) {
  return value === undefined ? "--" : integer.format(value);
}

const trendLabels = /** @type {Record<string, string>} */ ({
  rising: "上升",
  stable: "保持稳定",
  falling: "下降",
  insufficient: "样本不足",
});

/** @param {Partial<import("./analysisDashboardContracts").ReportIssueMetrics>} metrics */
export function issueMetricSummary(metrics) {
  const parts = [
    `命中 ${feedbackCount(metrics.matched_return_samples)} / ${feedbackCount(
      metrics.scoped_return_samples,
    )} 条反馈，占当前样本 ${percentage(metrics.return_sample_share)}`,
  ];
  if (
    metrics.gap_percentage_points !== null &&
    metrics.gap_percentage_points !== undefined
  ) {
    parts.push(`较同口径基线 ${percentagePoints(metrics.gap_percentage_points)}`);
  }
  if (
    metrics.recent_change_percentage_points !== null &&
    metrics.recent_change_percentage_points !== undefined
  ) {
    parts.push(`近期变化 ${percentagePoints(metrics.recent_change_percentage_points)}`);
  }
  parts.push(`趋势${trendLabels[metrics.trend_direction || ""] || "待确认"}`);
  return `${parts.join("；")}。`;
}
