import { ReturnReasonInsightSummary } from "./ReturnReasonInsightSummary";
import { ReturnReasonInsightBaseline } from "./ReturnReasonInsightBaseline";

/** @typedef {ReturnType<typeof import("./returnReasonInsightsPresentation").returnReasonInsightsPresentation>} ReturnInsightsView */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").DashboardInsights} DashboardInsights */
/** @param {{route: DashboardRoute, data: DashboardInsights, view: ReturnInsightsView, loading: boolean, showDataInfo?: boolean, error?: string, detailLoading?: boolean, detailError?: string, evidenceReady?: boolean, analysisContext: string, onRetry: () => void | Promise<void>, onUpdateFilters: (changes: Partial<DashboardRoute>) => void}} props */
export function ReturnReasonInsightsOverview({
  route,
  data,
  view,
  loading,
  showDataInfo = false,
  error,
  detailLoading = false,
  detailError = "",
  evidenceReady = true,
  analysisContext,
  onRetry,
  onUpdateFilters,
}) {
  return (
    <>
      <ReturnReasonInsightSummary
        route={route}
        data={data}
        dateRange={view.dateRange}
        options={view.options}
        includedCount={view.includedCount}
        pendingCount={view.pendingCount}
        statusCounts={view.statusCounts}
        analysisContext={analysisContext}
        loading={loading}
        error={error}
        onRetry={onRetry}
        onUpdateFilters={onUpdateFilters}
      />
      {showDataInfo && (
        <ReturnReasonInsightBaseline
          route={route}
          data={data}
          loading={
            loading || detailLoading || (!evidenceReady && !error && !detailError)
          }
          error={error || detailError}
        />
      )}
    </>
  );
}
