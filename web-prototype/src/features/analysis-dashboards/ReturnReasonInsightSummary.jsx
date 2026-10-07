import { analysisContextTerms } from "./analysisContextPresentation";
import { ReturnReasonSummaryFilters } from "./ReturnReasonSummaryFilters";
import { ReturnReasonSummaryTrust } from "./ReturnReasonSummaryTrust";
import { ReturnReasonCommentStatuses } from "./ReturnReasonCommentStatuses";

/** @typedef {import("./analysisDashboardContracts").DashboardInsights} DashboardInsights */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").InsightDateRange} InsightDateRange */
/** @typedef {import("./analysisDashboardContracts").InsightFilterOptions} InsightFilterOptions */
/** @typedef {{route: DashboardRoute, data: DashboardInsights, dateRange: InsightDateRange, options: InsightFilterOptions, includedCount: number, pendingCount: number, statusCounts: Record<string, number> | null, analysisContext: string, loading: boolean, error?: string, onRetry: () => void | Promise<void>, onUpdateFilters: (changes: Partial<DashboardRoute>) => void}} ReturnReasonInsightSummaryProps */

/** @param {ReturnReasonInsightSummaryProps} props */
export function ReturnReasonInsightSummary(props) {
  const terms = analysisContextTerms(props.analysisContext);
  const feedbackGroups = props.data.counting_basis === "feedback_group";
  const countUnit = feedbackGroups ? "个反馈组" : "条";
  return (
    <>
      <ReturnReasonSummaryFilters
        route={props.route}
        dateRange={props.dateRange}
        options={props.options}
        onUpdateFilters={props.onUpdateFilters}
        terms={terms}
      />
      <ReturnReasonSummaryTrust
        data={props.data}
        includedCount={props.includedCount}
        pendingCount={props.pendingCount}
        loading={props.loading}
        error={props.error}
        onRetry={props.onRetry}
        terms={terms}
        feedbackGroups={feedbackGroups}
        countUnit={countUnit}
      />
      <ReturnReasonCommentStatuses
        statusCounts={props.statusCounts}
        feedbackGroups={feedbackGroups}
      />
    </>
  );
}
