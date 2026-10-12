import { InsightGenerationModal } from "./InsightGenerationModal";
import { dashboardReportSummary } from "./dashboardReportPolicy";
import { useEffect, useState } from "react";
import { dashboardApi } from "../../shared/api/dashboardApi";
import { DashboardQualityScope } from "./DashboardQualityScope";
import { errorMessage } from "./dashboardRequestErrors";

/** @param {Pick<ReturnType<typeof import("./useDashboardReportActions").useDashboardReportActions>, "generationForm" | "setGenerationForm" | "setGenerationOpen" | "submitReportGeneration" | "generationState"> & {dashboard:import("./analysisDashboardContracts").Dashboard,selectedVersion:import("./analysisDashboardContracts").DashboardVersion|null,analysisContext:ReturnType<typeof import("./analysisContextPresentation").dashboardAnalysisContext>}} props */
export function DashboardReportGeneration({
  dashboard,
  selectedVersion,
  generationForm,
  setGenerationForm,
  setGenerationOpen,
  submitReportGeneration,
  generationState,
  analysisContext,
}) {
  const [statuses, setStatuses] = useState(["ready"]);
  const [attempt, setAttempt] = useState(0);
  const [scope, setScope] = useState({
    loading: true,
    error: "",
    plan: /** @type {import("./dashboardCreateContracts").DashboardPlan | null} */ (
      null
    ),
  });
  const sourceIds = (selectedVersion?.source_snapshot ?? []).map(
    (source) => source.result_version_id,
  );
  const scopeKey = JSON.stringify({
    result_version_ids: sourceIds,
    filters: { ...selectedVersion?.filters, quality_status: statuses },
  });
  useEffect(() => {
    const controller = new AbortController();
    setScope((current) => ({ ...current, loading: true, error: "" }));
    dashboardApi
      .dashboardPreflight(JSON.parse(scopeKey), { signal: controller.signal })
      .then((plan) => {
        if (!controller.signal.aborted) setScope({ loading: false, error: "", plan });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setScope((current) => ({
            ...current,
            loading: false,
            error: errorMessage(error),
          }));
      });
    return () => controller.abort();
  }, [scopeKey, attempt]);
  const reportSummary =
    scope.plan?.summary ?? dashboardReportSummary(null, selectedVersion);
  return (
    <InsightGenerationModal
      form={generationForm}
      onChange={setGenerationForm}
      onClose={() => setGenerationOpen(false)}
      onSubmit={(event) => {
        event.preventDefault();
        if (scope.plan?.ready && !scope.loading && !scope.error)
          return submitReportGeneration(event, {
            filters: scope.plan.filters || {},
            plan_hash: scope.plan.plan_hash,
          });
      }}
      models={generationState.models}
      loading={generationState.loading}
      submitting={generationState.submitting}
      error={
        scope.error || generationState.error || scope.plan?.blockers?.[0]?.message || ""
      }
      ready={!scope.loading && !scope.error && scope.plan?.ready === true}
      scopeLabel={`${dashboard.name || "未命名看板"} · 当前数据`}
      includedRecords={Number(reportSummary.record_count || 0)}
      unitCount={Number(reportSummary.unit_count || 0)}
      pendingRecords={Number(reportSummary.pending_review_record_count || 0)}
      excludedRecords={Number(reportSummary.excluded_record_count || 0)}
      analysisContext={analysisContext}
      scopeStatuses={statuses}
      scopeControl={
        <>
          <DashboardQualityScope
            statuses={statuses}
            onChange={setStatuses}
            disabled={generationState.submitting}
          />
          <span role="status">
            {scope.loading ? "正在核对统计范围…" : "统计范围已更新"}
          </span>
          {scope.error && (
            <button type="button" onClick={() => setAttempt((value) => value + 1)}>
              重新检查范围
            </button>
          )}
        </>
      }
    />
  );
}
