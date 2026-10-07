import { SectionHeading } from "./AiInsightReportCommon";
import { BusinessIssueGrid } from "./AiInsightReportBusinessIssues";
import { ReportHotspotBenchmarks } from "./AiInsightReportHotspotBenchmarks";
import { ReportSizeTrend } from "./AiInsightReportSizeTrend";
import {
  DiagnosticFindingIntro,
  DiagnosticFindingConclusion,
  ReportAdditionalFindings,
} from "./AiInsightReportDiagnosticFindings";
/** @typedef {import("./analysisDashboardContracts").InsightEvidenceCatalog} InsightEvidenceCatalog */
/** @typedef {import("./analysisDashboardContracts").ReportBusinessIssue} ReportBusinessIssue */
/** @typedef {import("./analysisDashboardContracts").ReportFinding} ReportFinding */
/** @typedef {import("./analysisDashboardContracts").ReportTrendSummary} ReportTrendSummary */
/** @typedef {import("./AiInsightReportPresentation").SizeTrendRow} SizeTrendRow */
/** @typedef {import("./AiInsightReportHotspotBenchmarks").HotspotGroup} HotspotGroup */

/** @param {{diagnosticFinding?: ReportFinding, hasBusinessIssues: boolean, businessIssues: ReportBusinessIssue[], smallTrend: ReportTrendSummary, largeTrend: ReportTrendSummary, sizeTrend: SizeTrendRow[], hotspotBenchmarks: HotspotGroup[], otherFindings: ReportFinding[], catalog: InsightEvidenceCatalog, analysisContext: string}} props */
export function ReportDiagnosticsSection(props) {
  const { diagnosticFinding, hasBusinessIssues, businessIssues, analysisContext } =
    props;
  if (
    !diagnosticFinding &&
    !hasBusinessIssues &&
    props.sizeTrend.length === 0 &&
    props.otherFindings.length === 0
  )
    return null;
  return (
    <section className="ai-report-section" id="report-diagnostic">
      <SectionHeading
        number="02"
        title={diagnosticFinding?.title || "关键发现与业务含义"}
        description="比较时间变化和商品内部发生比例，避免把总量误当成整改优先级。"
      />
      <DiagnosticFindingIntro diagnosticFinding={diagnosticFinding} />
      {hasBusinessIssues && (
        <BusinessIssueGrid issues={businessIssues} analysisContext={analysisContext} />
      )}
      <ReportSizeTrend
        smallTrend={props.smallTrend}
        largeTrend={props.largeTrend}
        sizeTrend={props.sizeTrend}
        analysisContext={analysisContext}
      />
      <ReportHotspotBenchmarks groups={props.hotspotBenchmarks} />
      <DiagnosticFindingConclusion
        diagnosticFinding={diagnosticFinding}
        catalog={props.catalog}
      />
      <ReportAdditionalFindings otherFindings={props.otherFindings} />
    </section>
  );
}
