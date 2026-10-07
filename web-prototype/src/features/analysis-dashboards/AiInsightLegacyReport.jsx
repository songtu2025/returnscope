import {
  ReportActionsSection,
  ReportAppendix,
  ReportBoundarySection,
  ReportInformationSection,
} from "./AiInsightReportActions";
import { ReportDiagnosticsSection } from "./AiInsightReportDiagnostics";
import {
  ReportChapterNavigation,
  ReportCover,
  ReportExecutiveSummary,
  ReportStructureSection,
} from "./AiInsightReportOverview";
import { legacyReportSections } from "./legacyInsightReportPresentation";

/** @typedef {import("./analysisDashboardContracts").InsightReport} InsightReport */
/** @typedef {import("./analysisDashboardContracts").Dashboard} Dashboard */
/** @typedef {import("./analysisDashboardContracts").DashboardVersion} DashboardVersion */

/** @param {string} id */
function scrollTo(id) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

/** @param {{report: InsightReport, reports: InsightReport[], attempts?: InsightReport[], dashboard: Dashboard, version: DashboardVersion | null, analysisContext: string, onSelect: (reportId: string) => void}} props */
export function AiInsightLegacyReport({
  report,
  reports,
  attempts = [],
  dashboard,
  version,
  analysisContext,
  onSelect,
}) {
  const sections = legacyReportSections(report);
  return (
    <div className="ai-insight-report ai-generated-report">
      <ReportCover
        {...sections.cover}
        report={report}
        reports={reports}
        dashboard={dashboard}
        version={version}
        onSelect={onSelect}
      />
      <ReportChapterNavigation scrollTo={scrollTo} />
      <article className="ai-report-document">
        <ReportExecutiveSummary
          {...sections.summary}
          analysisContext={analysisContext}
        />
        <ReportStructureSection
          {...sections.structure}
          analysisContext={analysisContext}
        />
        <ReportDiagnosticsSection
          {...sections.diagnostics}
          analysisContext={analysisContext}
        />
        <ReportInformationSection {...sections.information} />
        <ReportActionsSection {...sections.actions} />
        <ReportBoundarySection {...sections.boundary} />
      </article>
      <ReportAppendix
        {...sections.appendix}
        attempts={attempts}
        report={report}
        onSelect={onSelect}
      />
    </div>
  );
}
