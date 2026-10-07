import { Sparkle } from "@phosphor-icons/react";
import { ReportStatus } from "./AiInsightReportCommon";
import { AiInsightDecisionReport } from "./AiInsightDecisionReport";
import { AiInsightLegacyReport } from "./AiInsightLegacyReport";
/** @typedef {import("./analysisDashboardContracts").InsightReport} InsightReport */
/** @typedef {import("./analysisDashboardContracts").Dashboard} Dashboard */
/** @typedef {import("./analysisDashboardContracts").DashboardDecisionState} DashboardDecisionState */
/** @typedef {import("./analysisDashboardContracts").DashboardVersion} DashboardVersion */
/** @typedef {{report: InsightReport | null, reports: InsightReport[], attempts?: InsightReport[], latestReport: InsightReport | null, dashboard: Dashboard, version: DashboardVersion | null, analysisContext: string, onGenerate: () => void | Promise<void>, onRetry: () => void | Promise<void>, onSelect: (reportId: string) => void, selectedIssueId: string, decisionState: DashboardDecisionState, onDecision: (issueId: string, status: string) => void | Promise<void>, onSelectIssue: (issueId: string) => void}} AiInsightReportProps */

/** @param {{onGenerate: () => void | Promise<void>}} props */
function InsightReportEmpty({ onGenerate }) {
  return (
    <section className="ai-report-empty-state">
      <Sparkle size={34} weight="duotone" />
      <h2>当前数据版本还没有 AI 洞察报告</h2>
      <p>生成尝试会保留过程记录，只有成功发布后才产生报告版本号。</p>
      <button className="primary-button" onClick={onGenerate}>
        生成第一版报告
      </button>
    </section>
  );
}

/** @param {AiInsightReportProps} props */
export function AiInsightReport(props) {
  const { report, latestReport, onGenerate, onRetry, onSelect } = props;
  if (!report) return <InsightReportEmpty onGenerate={onGenerate} />;
  if (report.status !== "completed") {
    return (
      <ReportStatus
        report={report}
        latestReport={latestReport}
        onRetry={onRetry}
        onSelect={onSelect}
      />
    );
  }
  if (report.prompt_version === "ai-return-insight-v6") {
    return (
      <AiInsightDecisionReport
        report={report}
        reports={props.reports}
        selectedIssueId={props.selectedIssueId}
        decisionState={props.decisionState}
        onDecision={props.onDecision}
        onSelect={onSelect}
        onSelectIssue={props.onSelectIssue}
        analysisContext={props.analysisContext}
      />
    );
  }
  return <AiInsightLegacyReport {...props} report={report} />;
}
