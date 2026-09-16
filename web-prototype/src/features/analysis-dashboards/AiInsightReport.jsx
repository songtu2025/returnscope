import { Sparkle } from "@phosphor-icons/react";

import {
  ReportActionsSection,
  ReportAppendix,
  ReportBoundarySection,
  ReportInformationSection,
} from "./AiInsightReportActions";
import { ReportStatus } from "./AiInsightReportCommon";
import { AiInsightDecisionReport } from "./AiInsightDecisionReport";
import { ReportDiagnosticsSection } from "./AiInsightReportDiagnostics";
import {
  ReportChapterNavigation,
  ReportCover,
  ReportExecutiveSummary,
  ReportStructureSection,
} from "./AiInsightReportOverview";
import {
  diagnosticMap,
  findingReasonCode,
  hotspotGroups,
  mergeSizeTrend,
  number,
  reasonSamples,
} from "./AiInsightReportPresentation";

/** @typedef {import("./analysisDashboardContracts").InsightReport} InsightReport */
/** @typedef {import("./analysisDashboardContracts").Dashboard} Dashboard */
/** @typedef {import("./analysisDashboardContracts").DashboardDecisionState} DashboardDecisionState */
/** @typedef {import("./analysisDashboardContracts").DashboardVersion} DashboardVersion */
/** @typedef {import("./analysisDashboardContracts").InsightReportEvidence} InsightReportEvidence */
/** @typedef {import("./analysisDashboardContracts").LegacyInsightReportContent} LegacyInsightReportContent */
/** @typedef {{report: InsightReport | null, reports: InsightReport[], attempts?: InsightReport[], latestReport: InsightReport | null, dashboard: Dashboard, version: DashboardVersion | null, onGenerate: () => void | Promise<void>, onRetry: () => void | Promise<void>, onSelect: (reportId: string) => void, selectedIssueId: string, decisionState: DashboardDecisionState, onDecision: (issueId: string, status: string) => void | Promise<void>, onSelectIssue: (issueId: string) => void}} AiInsightReportProps */

/** @param {AiInsightReportProps} props */
export function AiInsightReport({
  report,
  reports,
  attempts = /** @type {InsightReport[]} */ ([]),
  latestReport,
  dashboard,
  version,
  onGenerate,
  onRetry,
  onSelect,
  selectedIssueId,
  decisionState,
  onDecision,
  onSelectIssue,
}) {
  if (!report) {
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
        reports={reports}
        selectedIssueId={selectedIssueId}
        decisionState={decisionState}
        onDecision={onDecision}
        onSelect={onSelect}
        onSelectIssue={onSelectIssue}
      />
    );
  }

  const content = /** @type {LegacyInsightReportContent} */ (report.content ?? {});
  const evidence = /** @type {InsightReportEvidence} */ (report.evidence ?? {});
  const analysis = evidence.analysis ?? {};
  const source = evidence.source ?? {};
  const catalog = evidence.catalog ?? {};
  const summary = analysis.summary ?? {};
  const groups = analysis.label_group_breakdown ?? [];
  const findings = content.findings ?? [];
  const diagnostics = diagnosticMap(analysis);
  const businessIssues = analysis.business_issues ?? [];
  const hasBusinessIssues = businessIssues.length > 0;
  const structureFinding =
    findings.find((item) => item.kind === "structure") ?? findings[0];
  const diagnosticFinding = findings.find((item) => item.kind === "diagnostic");
  const informationFinding = findings.find((item) => item.kind === "information");
  const otherFindings = findings.filter(
    (item) =>
      item !== structureFinding &&
      item !== diagnosticFinding &&
      item !== informationFinding,
  );
  const primaryGroup = groups.find((item) => item.value !== "其他原因") ?? groups[0];
  const maxGroupCount = Math.max(...groups.map((item) => number(item.record_count)), 1);
  const sizeTrend = hasBusinessIssues
    ? []
    : mergeSizeTrend(diagnostics, source.date_range?.date_to);
  const hotspotBenchmarks = hasBusinessIssues ? [] : hotspotGroups(diagnostics);
  const smallTrend = diagnostics.get("FIT_TOO_SMALL")?.trend_summary ?? {};
  const largeTrend = diagnostics.get("FIT_TOO_LARGE")?.trend_summary ?? {};
  const informationReasonCode = findingReasonCode(informationFinding);
  const informationDiagnostic = diagnostics.get(informationReasonCode);
  const informationReason =
    informationDiagnostic?.selected_reason ??
    (analysis.reasons ?? []).find(
      (item) => String(item.value) === informationReasonCode,
    );
  const informationOpinions = informationDiagnostic?.semantic_profile?.opinions ?? [];
  const informationSamples = reasonSamples(informationDiagnostic);
  const productMapping = source.product_mapping ?? {};
  const textQuality = source.text_quality ?? report.quality_gate?.text_quality ?? {};
  const qualityStatus = report.quality_gate?.status;
  const decisionReadiness = report.quality_gate?.decision_readiness;
  const inputTokens = number(report.usage?.input_tokens);
  const outputTokens = number(report.usage?.output_tokens);
  const actionOrder = /** @type {Record<string, number>} */ ({
    "action.mapping": 0,
    "action.diagnostic": 1,
    "action.text_quality": 2,
    "action.information": 3,
    "action.scope": 4,
  });
  const actions = [...(content.actions ?? [])].sort((left, right) => {
    const priorityDifference =
      { P0: 0, P1: 1, P2: 2 }[left.priority] - { P0: 0, P1: 1, P2: 2 }[right.priority];
    return (
      priorityDifference || (actionOrder[left.id] ?? 99) - (actionOrder[right.id] ?? 99)
    );
  });
  const [primaryAction, ...followupActions] = actions;

  /** @param {string} id */
  const scrollTo = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="ai-insight-report ai-generated-report">
      <ReportCover
        report={report}
        reports={reports}
        dashboard={dashboard}
        version={version}
        content={content}
        source={source}
        qualityStatus={qualityStatus}
        decisionReadiness={decisionReadiness}
        onSelect={onSelect}
      />

      <ReportChapterNavigation scrollTo={scrollTo} />

      <article className="ai-report-document">
        <ReportExecutiveSummary
          content={content}
          summary={summary}
          source={source}
          productMapping={productMapping}
          textQuality={textQuality}
        />
        <ReportStructureSection
          structureFinding={structureFinding}
          groups={groups}
          primaryGroup={primaryGroup}
          maxGroupCount={maxGroupCount}
          catalog={catalog}
        />
        <ReportDiagnosticsSection
          diagnosticFinding={diagnosticFinding}
          hasBusinessIssues={hasBusinessIssues}
          businessIssues={businessIssues}
          smallTrend={smallTrend}
          largeTrend={largeTrend}
          sizeTrend={sizeTrend}
          hotspotBenchmarks={hotspotBenchmarks}
          otherFindings={otherFindings}
          catalog={catalog}
        />
        <ReportInformationSection
          informationFinding={informationFinding}
          informationDiagnostic={informationDiagnostic}
          informationReason={informationReason}
          informationOpinions={informationOpinions}
          informationSamples={informationSamples}
          catalog={catalog}
        />
        <ReportActionsSection
          primaryAction={primaryAction}
          followupActions={followupActions}
          informationFinding={informationFinding}
          informationDiagnostic={informationDiagnostic}
          informationReason={informationReason}
        />
        <ReportBoundarySection content={content} />
      </article>

      <ReportAppendix
        attempts={attempts}
        report={report}
        inputTokens={inputTokens}
        outputTokens={outputTokens}
        onSelect={onSelect}
      />
    </div>
  );
}
