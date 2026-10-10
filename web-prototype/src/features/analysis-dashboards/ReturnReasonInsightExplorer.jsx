import { useMemo, useState } from "react";
import { analysisContextTerms } from "./analysisContextPresentation";
import { reasonPagePresentation } from "./returnReasonExplorerPresentation";
import { ReturnReasonExplorerFilters } from "./ReturnReasonExplorerFilters";
import { ReturnReasonExplorerRanking } from "./ReturnReasonExplorerRanking";
import { ReturnReasonExplorerHierarchy } from "./ReturnReasonExplorerHierarchy";
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
  const [hierarchyReset, setHierarchyReset] = useState(0);
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
        onReset={() => setHierarchyReset((value) => value + 1)}
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
        key={JSON.stringify([
          hierarchyReset,
          route.versionId,
          route.subject,
          route.labelGroup,
          route.listing,
          route.productName,
          route.productSku,
          route.dateFrom,
          route.dateTo,
        ])}
        hierarchy={props.hierarchy}
        selectedCode={pendingReason || view.activeReason?.value || ""}
        pendingReason={pendingReason}
        reasonStatus={reasonStatus}
        onUpdateRoute={props.onUpdateRoute}
      />
    </aside>
  );
}
