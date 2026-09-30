import { dashboardApi } from "../../shared/api/dashboardApi";

/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").DashboardInsights} DashboardInsights */
/** @typedef {import("./analysisDashboardContracts").DashboardContentData} DashboardContentData */
/** @typedef {import("./analysisDashboardContracts").DashboardContentState} DashboardContentState */
/** @typedef {{tab: DashboardRoute["tab"], overviewScope: string, scopeKey: string}} ContentContext */
/** @typedef {Pick<DashboardRoute, "dashboardId" | "versionId" | "tab">} ContentRoute */

/** @param {ContentRoute} route @param {Record<string, string>} filters @returns {ContentContext} */
export function dashboardContentContext(route, filters) {
  return {
    tab: route.tab,
    overviewScope: JSON.stringify([route.dashboardId, route.versionId]),
    scopeKey: JSON.stringify([
      route.dashboardId,
      route.versionId,
      filters.label_group,
      filters.subject,
      filters.listing,
      filters.product_name,
      filters.product_sku,
      filters.date_from,
      filters.date_to,
    ]),
  };
}

/** @param {DashboardContentData | null} data @param {ContentContext} [context] @returns {DashboardContentState} */
export function completedDashboardContent(
  data,
  context = { tab: "history", overviewScope: "", scopeKey: "" },
) {
  const overview = context.tab === "overview";
  return {
    loading: false,
    error: "",
    data,
    overviewScope: overview ? context.overviewScope : "",
    scopeKey: overview ? context.scopeKey : "",
    detailLoading: false,
    detailError: "",
  };
}

/** @param {DashboardContentState} current @param {ContentContext} context @param {DashboardInsights | null} cachedOverview @returns {DashboardContentState} */
export function pendingDashboardContent(current, context, cachedOverview) {
  const keepPrevious =
    context.tab === "overview" && current.overviewScope === context.overviewScope;
  const reasonOnly =
    keepPrevious &&
    current.data !== null &&
    cachedOverview !== null &&
    current.scopeKey === context.scopeKey;
  return {
    loading: !reasonOnly,
    error: "",
    data: keepPrevious ? current.data : null,
    overviewScope: context.tab === "overview" ? context.overviewScope : "",
    scopeKey: keepPrevious ? current.scopeKey : "",
    detailLoading: reasonOnly,
    detailError: "",
  };
}

/** @param {DashboardContentState} current @param {string} error @returns {DashboardContentState} */
export function failedDashboardContent(current, error) {
  return current.detailLoading
    ? { ...current, detailLoading: false, detailError: error }
    : { ...current, loading: false, error };
}

/** @param {DashboardInsights} overview @param {string} problem */
function selectedInsightReason(overview, problem) {
  return (
    overview.reasons?.find((reason) => reason.value === problem) ??
    overview.reasons?.[0]
  );
}

/**
 * @param {{route: ContentRoute, filters: Record<string, string>, cachedOverview: DashboardInsights | null, signal: AbortSignal, onOverview: (overview: DashboardInsights) => void}} options
 * @returns {Promise<{resetCategory: true} | {data: DashboardContentData}>}
 */
export async function loadDashboardContent({
  route,
  filters,
  cachedOverview,
  signal,
  onOverview,
}) {
  if (route.tab === "source") {
    return {
      data: await dashboardApi.analysisDashboardSources(
        route.dashboardId,
        route.versionId,
        { signal },
      ),
    };
  }
  let overview = cachedOverview;
  if (!overview) {
    overview = await dashboardApi.analysisDashboardInsights(
      route.dashboardId,
      route.versionId,
      { ...filters, problem: "", part: "overview" },
      { signal },
    );
    if (!overview) throw new Error("看板总览为空");
    // 旧响应既不能写入缓存，也不能继续发起原因请求。
    signal.throwIfAborted();
    onOverview(overview);
  }
  if (
    filters.label_group &&
    overview.category_groups?.length &&
    !overview.category_groups.includes(filters.label_group)
  ) {
    return { resetCategory: true };
  }
  const selected = selectedInsightReason(overview, filters.problem);
  if (!selected) return { data: overview };
  const detail = await dashboardApi.analysisDashboardInsights(
    route.dashboardId,
    route.versionId,
    { ...filters, problem: selected.value, part: "reason" },
    { signal },
  );
  return { data: { ...overview, ...detail, selected_reason: selected } };
}

/** @param {DashboardContentState} content @param {DashboardRoute} route */
export function dashboardEvidenceReady(content, route) {
  if (
    !content.data ||
    content.loading ||
    content.error ||
    content.detailLoading ||
    content.detailError
  ) {
    return false;
  }
  // 在副作用设置加载状态之前，也要阻止新筛选与旧结果混用。
  const context = dashboardContentContext(route, {
    label_group: route.labelGroup,
    subject: route.subject,
    listing: route.listing,
    product_name: route.productName,
    product_sku: route.productSku,
    date_from: route.dateFrom,
    date_to: route.dateTo,
  });
  if (content.scopeKey !== context.scopeKey) return false;
  const insights = /** @type {DashboardInsights} */ (content.data);
  return (
    insights.selected_reason?.value ===
    selectedInsightReason(insights, route.problem)?.value
  );
}
