import { analysisContextTerms } from "./analysisContextPresentation";
import { decisionReportView } from "./decisionReportPresentation";
import {
  DecisionIssueHeading,
  DecisionReportEmpty,
  DecisionReportHeader,
} from "./AiInsightDecisionHeader";
import { DecisionQueue } from "./AiInsightDecisionQueue";
import { DecisionMetrics } from "./AiInsightDecisionMetrics";
import { DecisionEvidence, DecisionEvidenceTrust } from "./AiInsightDecisionEvidence";
import { DecisionActions } from "./AiInsightDecisionActions";
export { InsightReportVersionSelect } from "./AiInsightDecisionHeader";
/** @typedef {import("./analysisDashboardContracts").DashboardDecisionState} DashboardDecisionState */
/** @typedef {import("./analysisDashboardContracts").InsightReport} InsightReport */
/** @typedef {import("./analysisDashboardContracts").DecisionReportIssue} DecisionReportIssue */
/** @typedef {ReturnType<typeof decisionReportView>} DecisionReportView */
/** @typedef {ReturnType<typeof analysisContextTerms>} AnalysisContextTerms */

/** @param {{report: InsightReport, view: DecisionReportView, selectedIssue: DecisionReportIssue, terms: AnalysisContextTerms, decisionState: DashboardDecisionState, onDecision: (issueId: string, status: string) => void | Promise<void>}} props */
function DecisionReportDetail({
  report,
  view,
  selectedIssue,
  terms,
  decisionState,
  onDecision,
}) {
  const { source, catalog, selectedDecision, readiness } = view;
  return (
    <article className="ai-decision-detail">
      <DecisionIssueHeading
        selectedIssue={selectedIssue}
        selectedDecision={selectedDecision}
      />
      <DecisionMetrics metrics={selectedIssue.metrics ?? {}} terms={terms} />
      <DecisionEvidenceTrust report={report} source={source} readiness={readiness} />
      <DecisionEvidence selectedIssue={selectedIssue} catalog={catalog} terms={terms} />
      <DecisionActions
        selectedIssue={selectedIssue}
        selectedDecision={selectedDecision}
        decisionState={decisionState}
        readiness={readiness}
        onDecision={onDecision}
      />
    </article>
  );
}

/** @param {{report: InsightReport, reports: InsightReport[], selectedIssueId: string, decisionState: DashboardDecisionState, analysisContext: string, onDecision: (issueId: string, status: string) => void | Promise<void>, onSelect: (reportId: string) => void, onSelectIssue: (issueId: string) => void}} props */
export function AiInsightDecisionReport({
  report,
  reports,
  selectedIssueId,
  decisionState,
  analysisContext,
  onDecision,
  onSelect,
  onSelectIssue,
}) {
  const terms = analysisContextTerms(analysisContext);
  const view = decisionReportView(report, selectedIssueId);
  const { selectedIssue } = view;
  if (!selectedIssue) return <DecisionReportEmpty />;

  return (
    <section className="ai-decision-report" aria-labelledby="ai-decision-report-title">
      <DecisionReportHeader
        report={report}
        reports={reports}
        onSelect={onSelect}
        view={view}
      />
      <div className="ai-decision-workbench">
        <DecisionQueue
          report={report}
          issues={view.issues}
          selectedIssue={selectedIssue}
          statusCounts={view.statusCounts}
          onSelectIssue={onSelectIssue}
        />
        <DecisionReportDetail
          report={report}
          view={view}
          selectedIssue={selectedIssue}
          terms={terms}
          decisionState={decisionState}
          onDecision={onDecision}
        />
      </div>
    </section>
  );
}
