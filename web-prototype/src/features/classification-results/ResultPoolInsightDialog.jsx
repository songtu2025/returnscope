import { InsightGenerationModal } from "../analysis-dashboards/InsightGenerationModal";
import { dashboardAnalysisContext } from "../analysis-dashboards/analysisContextPresentation";

/** @param {import("./classificationResultListContracts").ResultPoolContext} context */
export function ResultPoolInsightDialog(context) {
  const {
    insightForm,
    setInsightForm,
    setInsightOpen,
    submitInsight,
    insightState,
    selectedResults,
    selectedTotals,
  } = context;
  const counts = resultInsightCounts(insightState, selectedTotals);
  return (
    <InsightGenerationModal
      form={insightForm}
      onChange={setInsightForm}
      onClose={() => setInsightOpen(false)}
      onSubmit={submitInsight}
      models={insightState.models}
      loading={insightState.loading}
      submitting={insightState.submitting}
      error={resultInsightDialogError(insightState)}
      ready={insightState.plan?.ready === true}
      scopeLabel={resultInsightDialogScope(selectedResults)}
      includedRecords={counts.included}
      unitCount={selectedTotals.units}
      pendingRecords={counts.pending}
      excludedRecords={counts.excluded}
      analysisContext={dashboardAnalysisContext(insightState.plan?.sources ?? [], null)}
    />
  );
}

/** @param {import("./classificationResultListContracts").ResultPoolContext["insightState"]} insightState */
function resultInsightDialogError(insightState) {
  return (
    insightState.error ||
    insightState.plan?.blockers?.[0]?.message ||
    (insightState.plan?.conflicts?.length
      ? "所选结果包含同一 Listing 的重复版本，请调整选择。"
      : "")
  );
}
/** @param {import("./classificationResultListContracts").ResultPoolContext["selectedResults"]} selectedResults */
function resultInsightDialogScope(selectedResults) {
  return selectedResults.length === 1
    ? `${selectedResults[0].listing || "未提供 Listing"} · ${
        selectedResults[0].product_names?.[0] || "未提供产品名称"
      }`
    : `${selectedResults.length} 个分类结果版本`;
}
/** @param {import("./classificationResultListContracts").ResultPoolContext["insightState"]} insightState @param {import("./classificationResultListContracts").ResultPoolContext["selectedTotals"]} selectedTotals */
function resultInsightCounts(insightState, selectedTotals) {
  const summary = insightState.plan?.summary;
  return {
    included: Number(summary?.record_count ?? selectedTotals.records),
    pending: Number(summary?.pending_review_record_count || 0),
    excluded: Number(summary?.excluded_record_count || 0),
  };
}
