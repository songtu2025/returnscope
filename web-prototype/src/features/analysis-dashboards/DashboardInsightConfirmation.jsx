import { InsightGenerationModal } from "./InsightGenerationModal";
import { dashboardAnalysisContext } from "./analysisContextPresentation";
import { navigateHash } from "../../app/hashRouter";
import { DashboardQualityScope } from "./DashboardQualityScope";

/** @param {import("./dashboardCreateContracts").DashboardCreateContext & ReturnType<typeof import("./useDashboardInsightCreation").useDashboardInsightCreation>} context */
export function DashboardInsightConfirmation(context) {
  const {
    insightForm,
    setInsightForm,
    submitInsight,
    insightState,
    state,
    currentSources,
    summary,
    route,
    blockers,
    qualityStatuses,
    setQualityStatuses,
  } = context;
  return (
    <InsightGenerationModal
      form={insightForm}
      onChange={setInsightForm}
      onClose={() => {
        if (!insightState.submitting)
          navigateHash("classification-results", {
            selection_token: route.selectionToken,
          });
      }}
      onSubmit={submitInsight}
      models={insightState.models}
      loading={insightState.loading}
      submitting={insightState.submitting}
      error={blockers[0]?.message || insightState.error}
      ready={!state.loading && !state.error && state.plan?.ready === true}
      scopeLabel={
        currentSources.length === 1
          ? `${currentSources[0].listing || "未提供 Listing"} · ${currentSources[0].product_names?.[0] || "未提供产品名称"}`
          : `${currentSources.length} 个分类结果版本`
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
