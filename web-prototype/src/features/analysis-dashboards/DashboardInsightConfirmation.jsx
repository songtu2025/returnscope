import { InsightGenerationModal } from "./InsightGenerationModal";
import { dashboardAnalysisContext } from "./analysisContextPresentation";
import { navigateHash } from "../../app/hashRouter";
import { DashboardQualityScope } from "./DashboardQualityScope";
import { dashboardCreationReturn } from "./dashboardCreationRequests";

/** @param {import("./dashboardCreateContracts").DashboardCreateContext & ReturnType<typeof import("./useDashboardInsightCreation").useDashboardInsightCreation>} context */
export function DashboardInsightConfirmation(context) {
  const {
    insightForm,
    setInsightForm,
    submitInsight,
    insightState,
    reloadInsightModels,
    state,
    currentSources,
    summary,
    route,
    selection,
    blockers,
    qualityStatuses,
    setQualityStatuses,
  } = context;
  return (
    <InsightGenerationModal
      form={insightForm}
      onChange={setInsightForm}
      onClose={() => {
        if (!insightState.submitting) {
          const target = dashboardCreationReturn(selection, route.selectionToken);
          navigateHash(target.page, target.query);
        }
      }}
      onSubmit={submitInsight}
      models={insightState.models}
      modelError={insightState.modelError}
      onRetryModels={reloadInsightModels}
      loading={insightState.loading}
      submitting={insightState.submitting}
      error={blockers[0]?.message || insightState.error}
      ready={!state.loading && !state.error && state.plan?.ready === true}
      scopeLabel={
        currentSources.length === 1
          ? `${currentSources[0].listing || "未提供 Listing"}`
          : `${currentSources.length} 个分类结果`
      }
      includedRecords={Number(summary.record_count || 0)}
      unitCount={Number(summary.unit_count || 0)}
      pendingRecords={Number(summary.pending_review_record_count || 0)}
      excludedRecords={Number(summary.excluded_record_count || 0)}
      scopeControl={
        <DashboardQualityScope
          statuses={qualityStatuses}
          onChange={setQualityStatuses}
          disabled={insightState.submitting}
        />
      }
      scopeStatuses={qualityStatuses}
      analysisContext={dashboardAnalysisContext(currentSources, null)}
    />
  );
}
