import { returnReasonInsightsPresentation } from "./returnReasonInsightsPresentation";
import { useReturnReasonEvidence } from "./useReturnReasonEvidence";
import { ReturnReasonInsightsOverview } from "./ReturnReasonInsightsOverview";
import { ReturnReasonInsightWorkbench } from "./ReturnReasonInsightWorkbench";

/** @typedef {import("./analysisDashboardContracts").DashboardInsights} DashboardInsights */
/** @typedef {import("./analysisDashboardContracts").DashboardRecord} DashboardRecord */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").UpdateDashboardRoute} UpdateDashboardRoute */
/** @param {{route: DashboardRoute, updateRoute: UpdateDashboardRoute, data: DashboardInsights, loading: boolean, showDataInfo?: boolean, error?: string, detailLoading?: boolean, detailError?: string, evidenceReady?: boolean, analysisContext: string, onRetry: () => void | Promise<void>, onEvidence: (record: DashboardRecord, trigger: HTMLElement | null) => void}} props */
export function ReturnReasonInsights(props) {
  const {
    route,
    data,
    updateRoute: replaceRoute,
    evidenceReady = true,
    detailLoading = false,
  } = props;
  const view = returnReasonInsightsPresentation(data);
  const evidenceView = useReturnReasonEvidence({
    route,
    selected: view.explorer.selected,
    evidenceReady,
    evidence: view.evidence,
  });
  /** @param {Partial<DashboardRoute>} changes */
  const updateRoute = (changes) => replaceRoute(changes, { replace: true });
  /** @param {Partial<DashboardRoute>} changes */
  const updateFilters = (changes) =>
    updateRoute({
      ...changes,
      problem: changes.problem ?? route.problem,
      recordPage: 1,
      reasonPage: 0,
      hierarchyPage: 1,
    });
  return (
    <div
      className="return-insight-content"
      role="region"
      aria-label="语义洞察结果"
      aria-busy={props.loading || detailLoading}
    >
      <div className="return-insight-refresh-body">
        <ReturnReasonInsightsOverview
          {...props}
          view={view}
          onUpdateFilters={updateFilters}
        />
        <ReturnReasonInsightWorkbench
          {...props}
          view={view}
          evidenceView={evidenceView}
          onUpdateRoute={updateRoute}
        />
      </div>
    </div>
  );
}
