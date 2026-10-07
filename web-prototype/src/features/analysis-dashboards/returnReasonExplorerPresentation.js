export const REASON_PAGE_SIZE = 10;
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").InsightReason} InsightReason */
/** @param {InsightReason[]} visibleReasons @param {DashboardRoute} route @param {InsightReason | undefined} selected @param {string} pendingReason */
export function reasonPagePresentation(visibleReasons, route, selected, pendingReason) {
  const reasonPageCount = Math.max(
    1,
    Math.ceil(visibleReasons.length / REASON_PAGE_SIZE),
  );
  const activeReason = pendingReason
    ? selected
    : visibleReasons.find((reason) => reason.value === route.problem) || selected;
  const pageReason =
    visibleReasons.find((reason) => reason.value === pendingReason) || activeReason;
  const selectedIndex = visibleReasons.findIndex(
    (reason) => reason.value === pageReason?.value,
  );
  const selectedReasonPage =
    selectedIndex < 0 ? 1 : Math.floor(selectedIndex / REASON_PAGE_SIZE) + 1;
  const currentReasonPage = Math.min(
    route.reasonPage || selectedReasonPage,
    reasonPageCount,
  );
  const reasonPageStart = (currentReasonPage - 1) * REASON_PAGE_SIZE;
  const topReasonCount = Math.max(
    ...visibleReasons.map((item) => item.record_count),
    1,
  );
  return {
    visibleReasons,
    reasonPageCount,
    activeReason,
    currentReasonPage,
    reasonPageStart,
    topReasonCount,
  };
}
