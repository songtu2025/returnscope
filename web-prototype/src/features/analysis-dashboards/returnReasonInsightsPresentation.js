import { commentStatusCounts, orderGroups } from "./returnReasonInsightPresentation";

/** @param {import("./analysisDashboardContracts").DashboardInsights} data */
function explorerPresentation(data) {
  const reasons = data.reasons ?? [];
  const taxonomyLabels = new Map(
    (data.taxonomy?.labels ?? []).map((label) => [label.code, label]),
  );
  const selected = data.selected_reason;
  const subjects = data.subject_breakdown ?? [];
  const groups = orderGroups(data.category_groups ?? []);
  return { reasons, taxonomyLabels, selected, subjects, groups };
}

/** @param {import("./analysisDashboardContracts").DashboardInsights} data */
function overviewPresentation(data) {
  const summary = data.summary ?? {};
  const options = data.filter_options ?? {};
  const dateRange = data.date_range ?? {};
  const includedCount = Number(
    summary.comment_count ?? summary.record_count ?? data.total_comment_count ?? 0,
  );
  const pendingCount = Number(
    summary.pending_review_comment_count ?? summary.pending_review_record_count ?? 0,
  );
  const statusCounts = commentStatusCounts(data, summary);

  return {
    dateRange,
    options,
    includedCount,
    pendingCount,
    statusCounts,
  };
}

/** @param {import("./analysisDashboardContracts").DashboardInsights} data */
export function returnReasonInsightsPresentation(data) {
  const explorer = explorerPresentation(data);
  const products = data.products ?? [];
  const coReasons = data.co_reasons ?? [];
  const semanticProfile = data.semantic_profile ?? {};
  const evidence = data.evidence ?? { items: [], total: 0 };
  return {
    ...overviewPresentation(data),
    evidence,
    subjects: explorer.subjects,
    explorer,
    diagnostic: { selected: explorer.selected, products, coReasons, semanticProfile },
  };
}
