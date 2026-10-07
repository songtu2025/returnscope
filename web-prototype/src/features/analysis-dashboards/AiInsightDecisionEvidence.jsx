import {
  Check,
  ClockCountdown,
  Database,
  Question,
  ShieldCheck,
  WarningCircle,
} from "@phosphor-icons/react";
import { number, percentage, READINESS_LABELS } from "./decisionReportPresentation";
/** @typedef {import("./analysisDashboardContracts").InsightReport} InsightReport */
/** @typedef {import("./analysisDashboardContracts").InsightReportSource} InsightReportSource */
/** @typedef {import("./analysisDashboardContracts").ReportReadiness} ReportReadiness */
/** @typedef {import("./analysisDashboardContracts").InsightEvidenceCatalog} InsightEvidenceCatalog */
/** @typedef {import("./analysisDashboardContracts").DecisionReportIssue} DecisionReportIssue */
/** @typedef {ReturnType<typeof import("./analysisContextPresentation").analysisContextTerms>} AnalysisContextTerms */

/** @param {{report: InsightReport, source: InsightReportSource, readiness: ReportReadiness}} props */
export function DecisionEvidenceTrust({ report, source, readiness }) {
  const pendingReviewCount = number(source.pending_review_record_count);
  return (
    <section
      className={`ai-decision-trust ${report.quality_gate?.status || "warning"}`}
    >
      <div>
        <ShieldCheck size={22} weight="duotone" />
        <span>证据可信状态</span>
        <strong>{readiness.label || READINESS_LABELS[readiness.status]}</strong>
        <small>{readiness.reason}</small>
      </div>
      <ul>
        <li>
          <Check size={15} /> 已纳入 {number(source.included_record_count)} /{" "}
          {number(source.total_record_count)} 条记录
        </li>
        <li>
          <Check size={15} /> 标签覆盖 {percentage(source.label_coverage)}
        </li>
        {pendingReviewCount > 0 && (
          <li className="warning">
            <WarningCircle size={15} /> {pendingReviewCount} 条待审核未纳入统计
          </li>
        )}
      </ul>
    </section>
  );
}

/** @param {{selectedIssue: DecisionReportIssue}} props */
function DecisionEvidenceColumns({ selectedIssue }) {
  return (
    <div className="ai-decision-evidence-columns">
      <div>
        <h4>
          <Check size={17} /> 已经知道
        </h4>
        <ul>
          {(selectedIssue.known ?? []).map((item) => (
            <li key={item}>
              <Check size={14} /> {item}
            </li>
          ))}
        </ul>
        <p>{selectedIssue.evidence_explanation}</p>
      </div>
      <div>
        <h4>
          <ClockCountdown size={17} /> 还不知道
        </h4>
        <ul>
          {(selectedIssue.unknown ?? []).map((item) => (
            <li key={item}>
              <Question size={14} /> {item}
            </li>
          ))}
        </ul>
        <p className="ai-decision-hypothesis">
          当前只能提出验证问题，不能据此直接决定如何改商品。
        </p>
      </div>
    </div>
  );
}

/** @param {{selectedIssue: DecisionReportIssue, catalog: InsightEvidenceCatalog, terms: AnalysisContextTerms}} props */
function DecisionEvidenceDetails({ selectedIssue, catalog, terms }) {
  return (
    <footer>
      <span>口径：多标签占比不可直接相加，也{terms.rateBoundary}。</span>
      <details>
        <summary>
          <Database size={15} />
          <span className="ai-evidence-expand-label">
            查看 {selectedIssue.evidence_ids.length} 项证据
          </span>
          <span className="ai-evidence-collapse-label">
            收起 {selectedIssue.evidence_ids.length} 项证据
          </span>
        </summary>
        <ul aria-label="证据明细">
          {selectedIssue.evidence_ids.map((evidenceId) => (
            <li key={evidenceId}>
              <b>{catalog[evidenceId]?.label || evidenceId}</b>
              <span>{catalog[evidenceId]?.value || "结构化证据"}</span>
            </li>
          ))}
        </ul>
      </details>
    </footer>
  );
}

/** @param {{selectedIssue: DecisionReportIssue, catalog: InsightEvidenceCatalog, terms: AnalysisContextTerms}} props */
export function DecisionEvidence({ selectedIssue, catalog, terms }) {
  return (
    <section className="ai-decision-evidence">
      <header>
        <strong>证据摘要</strong>
        <span>已知事实与未知问题分开呈现</span>
      </header>
      <DecisionEvidenceColumns selectedIssue={selectedIssue} />
      <DecisionEvidenceDetails
        selectedIssue={selectedIssue}
        catalog={catalog}
        terms={terms}
      />
    </section>
  );
}
