import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import "../../styles/analysis-dashboards.css";
import {
  CaretRight,
  ChartBar,
  FunnelSimple,
  MagnifyingGlass,
} from "@phosphor-icons/react";
import Button from "antd/es/button";
import Input from "antd/es/input";
import useSWR from "swr";

import { navigateHash } from "../../app/hashRouter";
import { AntdProvider } from "../../components/AntdProvider";
import { Pagination } from "../../components/Pagination";
import { EmptyState, InlineLoading, PageHeading } from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";
import { PAGE_SIZES } from "../../shared/pagination";
import { dashboardApi } from "../../shared/api/dashboardApi";
import { serverStateKeys } from "../../shared/serverState";
import { DashboardCreateFlow } from "./DashboardCreateFlow";
import { DashboardDetailLoading } from "./DashboardDetailStateViews";
import { createDashboardSelection } from "./dashboardSelectionStorage";

/** @typedef {import("../../app/navigation").AppRoute} AppRoute */
/** @typedef {import("./analysisDashboardContracts").DashboardListItem} DashboardListItem */
/** @typedef {import("./analysisDashboardContracts").DashboardListPage} DashboardListPage */
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
    problem: query.problem || "",
    labelGroup: query.label_group || "",
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
      problem: route.problem,
      label_group: route.labelGroup,
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

/** @param {{route: DashboardRoute, updateRoute: UpdateDashboardRoute, userId: string}} props */
function DashboardList({ route, updateRoute, userId }) {
  const [filters, setFilters] = useState({ q: route.q, status: route.status });

  useEffect(
    () => setFilters({ q: route.q, status: route.status }),
    [route.q, route.status],
  );

  const query = useMemo(
    () => ({
      page: route.page,
      page_size: route.pageSize,
      q: route.q,
      status: route.status,
    }),
    [route.page, route.pageSize, route.q, route.status],
  );

  const { data, error, isLoading, isValidating, mutate } = useSWR(
    serverStateKeys.dashboardList(query),
    () => dashboardApi.analysisDashboards(query, {}),
    { keepPreviousData: true },
  );
  const message =
    error instanceof Error ? error.message : error ? "分析看板读取失败" : "";
  const load = () => mutate();

  const chooseResults = () => {
    const token = createDashboardSelection(userId);
    navigateHash("classification-results", { selection_token: token });
  };
  const dashboardData = /** @type {DashboardListPage | undefined} */ (data);
  const totalPages = Math.max(
    Math.ceil((dashboardData?.total ?? 0) / route.pageSize),
    1,
  );

  return (
    <div className="standard-page analysis-dashboard-page">
      <PageHeading
        eyebrow="可追溯分析交付"
        title="分析看板"
        description="从已发布、可用的分类结果版本生成不可变看板数据集。"
        action={
          <button className="primary-button" onClick={chooseResults}>
            <ChartBar size={18} /> 选择分类结果
          </button>
        }
      />

      <section className="dashboard-list-filters" aria-label="分析看板筛选">
        <label className="dashboard-filter-field">
          <span>关键词</span>
          <Input
            className="dashboard-list-search"
            aria-label="搜索分析看板"
            prefix={<MagnifyingGlass size={18} />}
            placeholder="搜索看板名称"
            value={filters.q}
            onChange={(event) => setFilters({ ...filters, q: event.target.value })}
          />
        </label>
        <label className="dashboard-filter-field">
          <span>看板状态</span>
          <select
            aria-label="看板状态"
            value={filters.status}
            onChange={(event) => setFilters({ ...filters, status: event.target.value })}
          >
            <option value="">全部状态</option>
            <option value="active">可用</option>
            <option value="archived">已归档</option>
          </select>
        </label>
        <Button
          type="primary"
          icon={<FunnelSimple size={17} />}
          onClick={() => updateRoute({ ...filters, page: 1 })}
        >
          筛选
        </Button>
      </section>

      <section className="dashboard-list-card">
        {isLoading && !dashboardData && <InlineLoading label="正在读取分析看板…" />}
        {message && (
          <div className="dashboard-error" role="alert">
            <b>
              {dashboardData
                ? "分析看板更新失败，当前显示上一次数据"
                : "分析看板读取失败"}
            </b>
            <span>{message}</span>
            <button className="secondary-button" onClick={load}>
              重新加载
            </button>
          </div>
        )}
        {!isLoading && dashboardData?.items.length === 0 && (
          <EmptyState
            icon={ChartBar}
            title={route.q || route.status ? "没有符合条件的看板" : "还没有分析看板"}
            description={
              route.q || route.status
                ? "调整筛选条件后重新查询。"
                : "先选择已发布、可用的分类结果版本生成第一份看板。"
            }
          />
        )}
        {dashboardData && dashboardData.items.length > 0 && (
          <>
            <div className={`dashboard-list-table ${isValidating ? "is-loading" : ""}`}>
              <div className="dashboard-list-head" role="row">
                <span>状态</span>
                <span>看板名称</span>
                <span>当前版本</span>
                <span>数据范围</span>
                <span>评论数</span>
                <span>最近更新</span>
                <span>创建人</span>
                <span>操作</span>
              </div>
              {dashboardData.items.map((dashboard) => (
                <DashboardRow
                  key={dashboard.id || dashboard.dashboard_id}
                  dashboard={dashboard}
                  onOpen={() =>
                    updateRoute({
                      dashboardId: dashboard.id || dashboard.dashboard_id,
                      versionId: dashboard.current_version_id || "",
                      tab: "overview",
                      page: 1,
                    })
                  }
                />
              ))}
            </div>
            <Pagination
              page={route.page}
              pageSize={route.pageSize}
              total={dashboardData.total}
              totalPages={totalPages}
              onPage={(page) => updateRoute({ page })}
              onPageSize={(pageSize) => updateRoute({ page: 1, pageSize })}
            />
          </>
        )}
      </section>
    </div>
  );
}

/** @param {{dashboard: DashboardListItem, onOpen: () => void}} props */
function DashboardRow({ dashboard, onOpen }) {
  const statusLabels = /** @type {Record<string, string>} */ ({
    active: "可用",
    archived: "已归档",
  });
  const summary = dashboard.summary ?? {};
  const status = dashboard.status || "active";
  return (
    <article className="dashboard-list-row" role="row">
      <span className={`dashboard-status ${status}`}>
        {statusLabels[status] || status}
      </span>
      <div>
        <b>{dashboard.name || "未命名看板"}</b>
        <small>{dashboard.description || "未提供说明"}</small>
      </div>
      <b>v{dashboard.current_version || dashboard.version || 1}</b>
      <span>{Number(summary.listing_count || 0).toLocaleString()} 个 Listing</span>
      <span>
        {Number(summary.comment_count ?? summary.record_count ?? 0).toLocaleString()}{" "}
        {summary.counting_basis === "feedback_group" ? "个反馈组" : "条"}
      </span>
      <span>{formatTime(dashboard.updated_at || dashboard.created_at)}</span>
      <span>{dashboard.created_by_name || "未提供"}</span>
      <button className="secondary-button compact-button" onClick={onOpen}>
        查看 <CaretRight size={15} />
      </button>
    </article>
  );
}
