import { useEffect, useState } from "react";

import { dashboardApi } from "../../shared/api/dashboardApi";
import { ReturnReasonInsightDiagnostic } from "./ReturnReasonInsightDiagnostic";
import { ReturnReasonInsightExplorer } from "./ReturnReasonInsightExplorer";
import { ReturnReasonInsightSummary } from "./ReturnReasonInsightSummary";
import { commentStatusCounts, orderGroups } from "./returnReasonInsightPresentation";

/** @typedef {import("./analysisDashboardContracts").DashboardInsights} DashboardInsights */
/** @typedef {import("./analysisDashboardContracts").DashboardRecord} DashboardRecord */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").UpdateDashboardRoute} UpdateDashboardRoute */
/** @param {{route: DashboardRoute, updateRoute: UpdateDashboardRoute, data: DashboardInsights, loading: boolean, error?: string, detailLoading?: boolean, detailError?: string, analysisContext: string, onRetry: () => void | Promise<void>, onEvidence: (record: DashboardRecord, trigger: HTMLElement | null) => void}} props */
export function ReturnReasonInsights({
  route,
  updateRoute: replaceRoute,
  data,
  loading,
  error,
  detailLoading = false,
  detailError = "",
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
  const evidencePageNumber = route.recordPage || 1;
  const [evidencePage, setEvidencePage] = useState(
    /** @returns {{key: string, data: import("./analysisDashboardContracts").InsightEvidence | null, loading: boolean, error: string}} */
    () => ({ key: "", data: null, loading: false, error: "" }),
  );
  const [evidenceRetry, setEvidenceRetry] = useState(0);
  const evidenceKey = JSON.stringify([
    route.dashboardId,
    route.versionId,
    selected?.value,
    route.labelGroup,
    route.listing,
    route.productName,
    route.productSku,
    route.dateFrom,
    route.dateTo,
    evidencePageNumber,
    evidenceRetry,
  ]);

  useEffect(() => {
    if (evidencePageNumber === 1 || !selected?.value) return;
    const controller = new AbortController();
    setEvidencePage({ key: evidenceKey, data: null, loading: true, error: "" });
    dashboardApi
      .analysisDashboardEvidence(
        route.dashboardId,
        route.versionId,
        {
          problem: selected.value,
          label_group: route.labelGroup,
          listing: route.listing,
          product_name: route.productName,
          product_sku: route.productSku,
          date_from: route.dateFrom,
          date_to: route.dateTo,
          page: evidencePageNumber,
        },
        { signal: controller.signal },
      )
      .then((response) => {
        if (!controller.signal.aborted) {
          setEvidencePage({
            key: evidenceKey,
            data: response,
            loading: false,
            error: "",
          });
        }
      })
      .catch((requestError) => {
        if (!controller.signal.aborted) {
          setEvidencePage({
            key: evidenceKey,
            data: null,
            loading: false,
            error:
              requestError instanceof Error
                ? requestError.message
                : String(requestError),
          });
        }
      });
    return () => controller.abort();
  }, [
    evidenceKey,
    evidencePageNumber,
    route.dashboardId,
    route.versionId,
    route.labelGroup,
    route.listing,
    route.productName,
    route.productSku,
    route.dateFrom,
    route.dateTo,
    selected?.value,
  ]);

  const currentEvidencePage = evidencePage.key === evidenceKey ? evidencePage : null;
  const visibleEvidence =
    evidencePageNumber === 1
      ? evidence
      : (currentEvidencePage?.data ?? { items: [], total: evidence.total });
  const evidenceLoading =
    evidencePageNumber > 1 && (!currentEvidencePage || currentEvidencePage.loading);
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
      reasonPage: 0,
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
          正在更新筛选结果，当前显示上一次结果…
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
            evidence={visibleEvidence}
            evidencePage={evidencePageNumber}
            evidenceLoading={evidenceLoading}
            evidenceError={currentEvidencePage?.error || ""}
            detailLoading={detailLoading}
            detailError={detailError}
            onDetailRetry={onRetry}
            onEvidencePage={(recordPage) => updateRoute({ recordPage })}
            onEvidenceRetry={() => setEvidenceRetry((value) => value + 1)}
            onUpdateRoute={updateRoute}
            onEvidence={onEvidence}
            analysisContext={analysisContext}
          />
        </div>
      </div>
    </div>
  );
}
