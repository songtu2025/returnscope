export const DECISION_LABELS = /** @type {Record<string, string>} */ ({
  pending: "待决策",
  ignored: "暂不处理",
  watching: "继续观察",
  verify: "待验证",
});

export const READINESS_LABELS = /** @type {Record<string, string>} */ ({
  unusable: "不可使用",
  diagnostic_only: "仅供诊断",
  verification_ready: "可进入验证",
});

/** @typedef {import("./analysisDashboardContracts").InsightReport} InsightReport */
/** @typedef {import("./analysisDashboardContracts").InsightDecisionReportContent} InsightDecisionReportContent */
/** @typedef {import("./analysisDashboardContracts").ReportIssueScope} ReportIssueScope */

/** @param {unknown} value */
export function number(value) {
  return Number.isFinite(Number(value)) ? Number(value) : 0;
}

/** @param {unknown} value @param {boolean} [signed] */
export function percentage(value, signed = false) {
  if (value === null || value === undefined) return "—";
  const parsed = number(value);
  return `${signed && parsed > 0 ? "+" : ""}${parsed.toFixed(1)}%`;
}

/** @param {unknown} value */
export function percentagePoints(value) {
  if (value === null || value === undefined) return "—";
  const parsed = number(value);
  return `${parsed > 0 ? "+" : ""}${parsed.toFixed(1)}pp`;
}

/** @param {InsightReport} report @param {string} issueId */
export function issueDecision(report, issueId) {
  return (
    (report.decisions ?? []).find((item) => item.issue_id === issueId)?.status ||
    "pending"
  );
}

/** @param {ReportIssueScope | undefined} scope */
export function scopeText(scope) {
  return (
    [scope?.listing, scope?.product, scope?.sku].filter(Boolean).join(" / ") ||
    "当前范围"
  );
}

/** @param {InsightReport} report @param {string} selectedIssueId */
export function decisionReportView(report, selectedIssueId) {
  const content = /** @type {InsightDecisionReportContent} */ (report.content ?? {});
  const source = report.evidence?.source ?? {};
  const catalog = report.evidence?.catalog ?? {};
  const issues = content.issues ?? [];
  const selectedIssue =
    issues.find((issue) => issue.id === selectedIssueId) ?? issues[0] ?? null;
  const selectedDecision = selectedIssue
    ? issueDecision(report, selectedIssue.id)
    : "pending";
  const readiness = selectedIssue?.readiness ??
    report.quality_gate?.decision_readiness ?? { status: "diagnostic_only" };
  const statusCounts = issues.reduce(
    (counts, issue) => {
      const status = issueDecision(report, issue.id);
      counts[status] = (counts[status] || 0) + 1;
      return counts;
    },
    /** @type {Record<string, number>} */ ({
      pending: 0,
      watching: 0,
      verify: 0,
      ignored: 0,
    }),
  );
  return {
    content,
    source,
    catalog,
    issues,
    selectedIssue,
    selectedDecision,
    readiness,
    statusCounts,
  };
}
