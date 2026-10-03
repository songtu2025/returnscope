import { InsightGenerationModal } from "./InsightGenerationModal";
import { dashboardVersionNumber } from "./dashboardFields";
import { dashboardReportSummary } from "./dashboardReportPolicy";

/** @param {Pick<ReturnType<typeof import("./useDashboardReportActions").useDashboardReportActions>, "generationForm" | "setGenerationForm" | "setGenerationOpen" | "submitReportGeneration" | "generationState"> & {dashboard:import("./analysisDashboardContracts").Dashboard,selectedVersion:import("./analysisDashboardContracts").DashboardVersion|null,selectedReport:import("./analysisDashboardContracts").InsightReport|null,analysisContext:ReturnType<typeof import("./analysisContextPresentation").dashboardAnalysisContext>}} props */
export function DashboardReportGeneration({
  dashboard,
  selectedVersion,
  selectedReport,
  generationForm,
  setGenerationForm,
  setGenerationOpen,
  submitReportGeneration,
  generationState,
  analysisContext,
}) {
  const reportSummary = dashboardReportSummary(selectedReport, selectedVersion);
  return (
    <InsightGenerationModal
      form={generationForm}
      onChange={setGenerationForm}
      onClose={() => setGenerationOpen(false)}
      onSubmit={submitReportGeneration}
      models={generationState.models}
      loading={generationState.loading}
      submitting={generationState.submitting}
      error={generationState.error}
      ready
      scopeLabel={`${dashboard.name || "未命名看板"} · 数据版本 v${dashboardVersionNumber(selectedVersion) || 1}`}
      includedRecords={Number(reportSummary.record_count || 0)}
      unitCount={Number(reportSummary.unit_count || 0)}
      pendingRecords={Number(reportSummary.pending_review_record_count || 0)}
      excludedRecords={Number(reportSummary.excluded_record_count || 0)}
      analysisContext={analysisContext}
    />
  );
}
