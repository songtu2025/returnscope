import { ReturnReasonInsightDiagnostic } from "./ReturnReasonInsightDiagnostic";
import { ReturnReasonInsightExplorer } from "./ReturnReasonInsightExplorer";

/** @typedef {ReturnType<typeof import("./returnReasonInsightsPresentation").returnReasonInsightsPresentation>} ReturnInsightsView */
/** @typedef {ReturnType<typeof import("./useReturnReasonEvidence").useReturnReasonEvidence>} ReturnEvidenceView */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").DashboardInsights} DashboardInsights */
/** @typedef {import("./analysisDashboardContracts").DashboardRecord} DashboardRecord */
/** @param {{route: DashboardRoute, data: DashboardInsights, view: ReturnInsightsView, evidenceView: ReturnEvidenceView, loading: boolean, detailLoading?: boolean, detailError?: string, analysisContext: string, onRetry: () => void | Promise<void>, onEvidence: (record: DashboardRecord, trigger: HTMLElement | null) => void, onUpdateRoute: (changes: Partial<DashboardRoute>) => void}} props */
export function ReturnReasonInsightWorkbench({
  route,
  data,
  view,
  evidenceView,
  loading,
  detailLoading = false,
  detailError = "",
  analysisContext,
  onRetry,
  onEvidence,
  onUpdateRoute,
}) {
  return (
    <div className="return-insight-workbench" inert={loading}>
      <ReturnReasonInsightExplorer
        {...view.explorer}
        route={route}
        data={data}
        pendingReason={detailLoading || detailError ? route.problem : ""}
        reasonStatus={detailError ? "更新失败" : "更新中"}
        onUpdateRoute={onUpdateRoute}
        analysisContext={analysisContext}
      />
      <ReturnReasonInsightDiagnostic
        {...view.diagnostic}
        {...evidenceView}
        data={data}
        subjectLabel={
          route.subject
            ? view.subjects.find((subject) => subject.value === route.subject)?.label
            : ""
        }
        detailLoading={detailLoading}
        detailError={detailError}
        onDetailRetry={onRetry}
        onEvidencePage={(recordPage) => onUpdateRoute({ recordPage })}
        onUpdateRoute={onUpdateRoute}
        onEvidence={onEvidence}
        analysisContext={analysisContext}
      />
    </div>
  );
}
