import { useMemo } from "react";
import { analysisContextTerms } from "./analysisContextPresentation";
import { reasonPagePresentation } from "./returnReasonExplorerPresentation";
import { ReturnReasonExplorerFilters } from "./ReturnReasonExplorerFilters";
import {
  ReturnReasonExplorerRanking,
  ReturnReasonExplorerHierarchy,
} from "./ReturnReasonExplorerRanking";
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewLabel} ReviewLabel */
/** @typedef {import("./analysisDashboardContracts").DashboardInsights} DashboardInsights */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").InsightHierarchyNode} InsightHierarchyNode */
/** @typedef {import("./analysisDashboardContracts").InsightReason} InsightReason */
/** @typedef {{route: DashboardRoute, data: DashboardInsights, reasons: InsightReason[], hierarchy: InsightHierarchyNode[], taxonomyLabels: Map<string, ReviewLabel>, selected?: InsightReason, subjects: InsightReason[], groups: string[], pendingReason?: string, reasonStatus?: string, analysisContext: string, onUpdateRoute: (changes: Partial<DashboardRoute>) => void}} ReturnReasonInsightExplorerProps */

/** @param {ReturnReasonInsightExplorerProps} props */
export function ReturnReasonInsightExplorer(props) {
  const {
    route,
    subjects,
    reasons,
    selected,
    pendingReason = "",
    reasonStatus = "更新中",
    analysisContext,
  } = props;
  const terms = analysisContextTerms(analysisContext);
  const selectedSubject = subjects.some((subject) => subject.value === route.subject)
    ? route.subject
    : "";
  const visibleReasons = useMemo(
    () =>
      selectedSubject
        ? reasons.filter((reason) => reason.subjects?.includes(selectedSubject))
        : reasons,
    [reasons, selectedSubject],
  );
  const view = reasonPagePresentation(visibleReasons, route, selected, pendingReason);
  return (
    <aside className="return-insight-explorer" aria-label={terms.reasonChooserAria}>
      <ReturnReasonExplorerFilters
        {...props}
        selectedSubject={selectedSubject}
        terms={terms}
      />
      <ReturnReasonExplorerRanking
        {...props}
        view={view}
        pendingReason={pendingReason}
        reasonStatus={reasonStatus}
        selectedSubject={selectedSubject}
        terms={terms}
      />
      <ReturnReasonExplorerHierarchy
        page={route.hierarchyPage}
        hierarchy={props.hierarchy}
        taxonomyLabels={props.taxonomyLabels}
        activeReason={view.activeReason}
        onUpdateRoute={props.onUpdateRoute}
      />
    </aside>
  );
}
