import { CaretRight } from "@phosphor-icons/react";
import {
  DECISION_LABELS,
  issueDecision,
  percentage,
  percentagePoints,
  scopeText,
} from "./decisionReportPresentation";
/** @typedef {import("./analysisDashboardContracts").InsightReport} InsightReport */
/** @typedef {import("./analysisDashboardContracts").DecisionReportIssue} DecisionReportIssue */

/** @param {{issue: DecisionReportIssue, selectedIssue: DecisionReportIssue, status: string, onSelectIssue: (issueId: string) => void}} props */
function DecisionQueueItem({ issue, selectedIssue, status, onSelectIssue }) {
  return (
    <li>
      <button
        className={issue.id === selectedIssue.id ? "active" : ""}
        onClick={() => onSelectIssue(issue.id)}
        aria-current={issue.id === selectedIssue.id ? "true" : undefined}
      >
        <span>
          {String(issue.rank).padStart(2, "0")} ·{" "}
          {issue.id === selectedIssue.id ? "当前选择" : DECISION_LABELS[status]}
        </span>
        <b>{issue.title}</b>
        <small>{scopeText(issue.scope)}</small>
        <em>
          {percentage(issue.metrics?.return_sample_share)} ·{" "}
          {percentagePoints(issue.metrics?.gap_percentage_points)}
        </em>
        <i>{DECISION_LABELS[status]}</i>
        <CaretRight size={16} />
      </button>
    </li>
  );
}

/** @param {{report: InsightReport, issues: DecisionReportIssue[], selectedIssue: DecisionReportIssue, statusCounts: Record<string, number>, onSelectIssue: (issueId: string) => void}} props */
export function DecisionQueue({
  report,
  issues,
  selectedIssue,
  statusCounts,
  onSelectIssue,
}) {
  return (
    <aside className="ai-decision-queue" aria-label="问题队列">
      <header>
        <div>
          <h3>问题队列</h3>
          <p>按确定性证据排序</p>
        </div>
        <b>{issues.length}</b>
      </header>
      <div className="ai-decision-queue-summary" aria-label="问题状态统计">
        <span>待决策 {statusCounts.pending}</span>
        <span>观察 {statusCounts.watching}</span>
        <span>待验证 {statusCounts.verify}</span>
      </div>
      <ol>
        {issues.map((issue) => (
          <DecisionQueueItem
            key={issue.id}
            issue={issue}
            selectedIssue={selectedIssue}
            status={issueDecision(report, issue.id)}
            onSelectIssue={onSelectIssue}
          />
        ))}
      </ol>
      <p className="ai-decision-queue-note">这里仅记录判断状态，不下发后续执行。</p>
    </aside>
  );
}
