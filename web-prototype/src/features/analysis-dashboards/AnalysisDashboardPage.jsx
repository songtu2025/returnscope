import { lazy, Suspense, useCallback, useEffect, useRef } from "react";
import "../../styles/analysis-dashboards.css";

import { navigateHash } from "../../app/hashRouter";
import { AntdProvider } from "../../components/AntdProvider";
import { PAGE_SIZES } from "../../shared/pagination";
import { DashboardList } from "./DashboardList";
import { DashboardCreateFlow } from "./DashboardCreateFlow";
import { DashboardDetailLoading } from "./DashboardDetailStateViews";

/** @typedef {import("../../app/navigation").AppRoute} AppRoute */
/** @typedef {import("./analysisDashboardContracts").DashboardNotify} DashboardNotify */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").DashboardTab} DashboardTab */
/** @typedef {import("./analysisDashboardContracts").UpdateDashboardRoute} UpdateDashboardRoute */

const DashboardDetail = lazy(() =>
  import("./DashboardDetail").then((module) => ({ default: module.DashboardDetail })),
);

const TABS = /** @type {Set<DashboardTab>} */ (
  new Set(["overview", "report", "source", "history"])
);

/** @param {Record<string, string | undefined>} query @returns {DashboardRoute} */
function routeState(query) {
  /** @param {string} key */
  const number = (key) => Number(query[key]);
  const tab = /** @type {DashboardTab} */ (
    TABS.has(/** @type {DashboardTab} */ (query.tab)) ? query.tab : "overview"
  );
  const step =
    query.step === "conflicts" || query.step === "confirm" ? query.step : "check";
  const reasonPage = number("reason_page");
  return {
    dashboardId: query.dashboard || "",
    versionId: query.version || "",
    reportId: query.report || "",
    issueId: query.issue || "",
    tab,
    selectionToken: query.selection_token || "",
    step,
    status: query.status || "",
    q: query.q || "",
    page: Math.max(number("page") || 1, 1),
    pageSize: PAGE_SIZES.includes(number("page_size")) ? number("page_size") : 20,
    recordPage: Math.max(number("record_page") || 1, 1),
    reasonPage: Number.isSafeInteger(reasonPage) && reasonPage > 0 ? reasonPage : 0,
    problem: query.problem || "",
    labelGroup: query.label_group || "",
    subject: query.subject || "",
    listing: query.listing || "",
    productName: query.product_name || "",
    productSku: query.product_sku || "",
    orderId: query.order_id || "",
    dateFrom: query.date_from || "",
    dateTo: query.date_to || "",
  };
}

/** @param {DashboardRoute} route @param {{replace?: boolean}} [options] */
function writeRoute(route, options) {
  navigateHash(
    "analysis-dashboards",
    {
      dashboard: route.dashboardId,
      version: route.versionId,
      report: route.reportId,
      issue: route.issueId,
      tab: route.tab === "overview" ? "" : route.tab,
      selection_token: route.selectionToken,
      step: route.selectionToken && route.step !== "check" ? route.step : "",
      status: route.status,
      q: route.q,
      page: route.page > 1 ? route.page : "",
      page_size: route.pageSize !== 20 ? route.pageSize : "",
      record_page: route.recordPage > 1 ? route.recordPage : "",
      reason_page: route.reasonPage > 0 ? route.reasonPage : "",
      problem: route.problem,
      label_group: route.labelGroup,
      subject: route.subject,
      listing: route.listing,
      product_name: route.productName,
      product_sku: route.productSku,
      order_id: route.orderId,
      date_from: route.dateFrom,
      date_to: route.dateTo,
    },
    options,
  );
}

/** @param {{route?: AppRoute | null, notify: DashboardNotify, userId: string}} props */
export function AnalysisDashboardPage({ route: appRoute, notify, userId }) {
  const route = routeState(appRoute?.query ?? {});
  const routeRef = useRef(route);
  useEffect(() => {
    routeRef.current = route;
  }, [route]);
  const updateRoute = useCallback(
    /** @type {UpdateDashboardRoute} */
    (changes, options) => writeRoute({ ...routeRef.current, ...changes }, options),
    [],
  );

  if (route.dashboardId) {
    return (
      <AntdProvider>
        <Suspense fallback={<DashboardDetailLoading />}>
          <DashboardDetail
            route={route}
            updateRoute={updateRoute}
            notify={notify}
            userId={userId}
          />
        </Suspense>
      </AntdProvider>
    );
  }
  if (route.selectionToken) {
    return (
      <DashboardCreateFlow
        route={route}
        updateRoute={updateRoute}
        notify={notify}
        userId={userId}
      />
    );
  }
  return (
    <AntdProvider>
      <DashboardList route={route} updateRoute={updateRoute} userId={userId} />
    </AntdProvider>
  );
}
