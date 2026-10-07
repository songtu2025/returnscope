import { WarningCircle } from "@phosphor-icons/react";
import { date } from "./AiInsightReportPresentation";
import {
  DECISION_LABELS,
  READINESS_LABELS,
  scopeText,
} from "./decisionReportPresentation";
/** @typedef {import("./analysisDashboardContracts").InsightReport} InsightReport */
/** @typedef {ReturnType<typeof import("./decisionReportPresentation").decisionReportView>} DecisionReportView */
/** @typedef {import("./analysisDashboardContracts").DecisionReportIssue} DecisionReportIssue */

/** @param {{report: InsightReport, reports: InsightReport[], onSelect: (reportId: string) => void, optionLabel: (report: InsightReport) => string}} props */
export function InsightReportVersionSelect({ report, reports, onSelect, optionLabel }) {
  if (reports.length <= 1) return null;

  return (
    <label>
      报告版本
      <select value={report.id} onChange={(event) => onSelect(event.target.value)}>
        {reports.map((item) => (
          <option key={item.id} value={item.id}>
            {optionLabel(item)}
          </option>
        ))}
      </select>
    </label>
  );
}

/** @param {{report: InsightReport, reports: InsightReport[], onSelect: (reportId: string) => void, view: DecisionReportView}} props */
export function DecisionReportHeader({ report, reports, onSelect, view }) {
  const { content, source, issues, readiness } = view;
  return (
    <header className="ai-decision-report-header">
      <div>
        <span>AI 洞察报告 · 报告 V{report.version_no}</span>
        <h2 id="ai-decision-report-title">{content.title}</h2>
        <p>
          {source.report_profile?.category_name || "通用品类"} · {issues.length} 个问题
          · {date(source.date_range?.date_from)}–{date(source.date_range?.date_to)}
        </p>
      </div>
      <div className="ai-decision-report-tools">
        <strong className={`ai-decision-readiness ${readiness.status}`}>
          {READINESS_LABELS[readiness.status] || readiness.label}
        </strong>
        <InsightReportVersionSelect
          report={report}
          reports={reports}
          onSelect={onSelect}
          optionLabel={(item) => `报告 V${item.version_no}`}
        />
      </div>
    </header>
  );
}

/** @param {{selectedIssue: DecisionReportIssue, selectedDecision: string}} props */
export function DecisionIssueHeading({ selectedIssue, selectedDecision }) {
  return (
    <>
      <header className="ai-decision-detail-header">
        <div>
          <span>问题 {String(selectedIssue.rank).padStart(2, "0")} · 当前选择</span>
          <h3>{selectedIssue.title}</h3>
          <p>{scopeText(selectedIssue.scope)}</p>
        </div>
        <strong className={`ai-decision-status ${selectedDecision}`}>
          {DECISION_LABELS[selectedDecision]}
        </strong>
      </header>

      <section className="ai-decision-question">
        <div>
          <span>需要你作出的判断</span>
          <h4>{selectedIssue.recommendation?.validation_question}</h4>
        </div>
        <b>约 3 分钟</b>
      </section>
    </>
  );
}

export function DecisionReportEmpty() {
  return (
    <section className="ai-report-empty-state">
      <WarningCircle size={34} weight="duotone" />
      <h2>当前报告没有可判断的问题</h2>
      <p>请检查分类结果覆盖或重新生成报告。</p>
    </section>
  );
}
