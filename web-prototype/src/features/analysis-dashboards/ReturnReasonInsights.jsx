import { ReturnReasonInsightDiagnostic } from "./ReturnReasonInsightDiagnostic";
import { ReturnReasonInsightExplorer } from "./ReturnReasonInsightExplorer";
import { ReturnReasonInsightSummary } from "./ReturnReasonInsightSummary";
import { commentStatusCounts, orderGroups } from "./returnReasonInsightPresentation";

/** @typedef {import("./analysisDashboardContracts").DashboardInsights} DashboardInsights */
/** @typedef {import("./analysisDashboardContracts").DashboardRecord} DashboardRecord */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").UpdateDashboardRoute} UpdateDashboardRoute */
/** @param {{route: DashboardRoute, updateRoute: UpdateDashboardRoute, data: DashboardInsights, loading: boolean, error?: string, analysisContext: string, onRetry: () => void | Promise<void>, onEvidence: (record: DashboardRecord, trigger: HTMLElement | null) => void}} props */
export function ReturnReasonInsights({
  route,
  updateRoute: replaceRoute,
  data,
  loading,
  error,
  analysisContext,
  onRetry,
  onEvidence,
}) {
  const summary = data.summary ?? {};
  const reasons = data.reasons ?? [];
  const hierarchy = data.hierarchy_problems ?? [];
  const taxonomyLabels = new Map(
    (data.taxonomy?.labels ?? []).map((label) => [label.code, label]),
  );
  const selected = data.selected_reason;
  const products = data.products ?? [];
  const coReasons = data.co_reasons ?? [];
  const semanticProfile = data.semantic_profile ?? {};
  const evidence = data.evidence ?? { items: [], total: 0 };
  const options = data.filter_options ?? {};
  const dateRange = data.date_range ?? {};
  const subjects = data.subject_breakdown ?? [];
  const groups = orderGroups(data.category_groups ?? []);
  const includedCount = Number(
    summary.comment_count ?? summary.record_count ?? data.total_comment_count ?? 0,
  );
  const pendingCount = Number(
    summary.pending_review_comment_count ?? summary.pending_review_record_count ?? 0,
  );
  const statusCounts = commentStatusCounts(data, summary);
  /** @param {Partial<DashboardRoute>} changes */
  const updateRoute = (changes) => replaceRoute(changes, { replace: true });

  /** @param {Partial<DashboardRoute>} changes */
  const updateFilters = (changes) =>
    updateRoute({
      ...changes,
      problem: changes.problem ?? route.problem,
      recordPage: 1,
    });

  return (
    <div
      className="return-insight-content"
      role="region"
      aria-label="语义洞察结果"
      aria-busy={loading}
    >
      {loading && (
        <div className="return-insight-refresh-status" role="status" aria-live="polite">
          正在更新筛选结果…
        </div>
      )}
      {!loading && error && (
        <div className="return-insight-refresh-error" role="alert">
          <span>更新失败，当前显示上一次结果。</span>
          <button type="button" className="text-button" onClick={onRetry}>
            重试
          </button>
        </div>
      )}
      <div className={`return-insight-refresh-body ${loading ? "is-loading" : ""}`}>
        <ReturnReasonInsightSummary
          route={route}
          data={data}
          dateRange={dateRange}
          options={options}
          includedCount={includedCount}
          pendingCount={pendingCount}
          statusCounts={statusCounts}
          loading={loading}
          analysisContext={analysisContext}
          onUpdateFilters={updateFilters}
        />

        <div className="return-insight-workbench">
          <ReturnReasonInsightExplorer
            route={route}
            data={data}
            reasons={reasons}
            hierarchy={hierarchy}
            taxonomyLabels={taxonomyLabels}
            selected={selected}
            subjects={subjects}
            groups={groups}
            onUpdateRoute={updateRoute}
            analysisContext={analysisContext}
          />
          <ReturnReasonInsightDiagnostic
            data={data}
            selected={selected}
            products={products}
            coReasons={coReasons}
            semanticProfile={semanticProfile}
            evidence={evidence}
            onUpdateRoute={updateRoute}
            onEvidence={onEvidence}
            analysisContext={analysisContext}
          />
        </div>
      </div>
    </div>
  );
}
