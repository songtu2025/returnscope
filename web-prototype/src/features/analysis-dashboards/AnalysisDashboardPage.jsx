import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CaretRight,
  ChartBar,
  FunnelSimple,
  MagnifyingGlass,
} from "@phosphor-icons/react";

import { navigateHash } from "../../app/hashRouter";
import { EmptyState, InlineLoading, PageHeading } from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";
import { dashboardApi } from "../../shared/api/dashboardApi";
import { DashboardCreateFlow } from "./DashboardCreateFlow";
import { DashboardDetail } from "./DashboardDetail";
import { DashboardPagination } from "./DashboardPagination";
import { createDashboardSelection } from "./dashboardSelectionStorage";

const PAGE_SIZES = [20, 50, 100];
const TABS = new Set(["overview", "report", "source", "history"]);

function routeState(query) {
  const number = (key) => Number(query[key]);
  return {
    dashboardId: query.dashboard || "",
    versionId: query.version || "",
    reportId: query.report || "",
    tab: TABS.has(query.tab) ? query.tab : "overview",
    selectionToken: query.selection_token || "",
    step: ["check", "conflicts", "confirm"].includes(query.step) ? query.step : "check",
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

function writeRoute(route, options) {
  navigateHash(
    "analysis-dashboards",
    {
      dashboard: route.dashboardId,
      version: route.versionId,
      report: route.reportId,
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

export function AnalysisDashboardPage({ route: appRoute, notify, userId }) {
  const route = routeState(appRoute?.query ?? {});
  const updateRoute = useCallback(
    (changes, options) => writeRoute({ ...route, ...changes }, options),
    [route],
  );

  if (route.dashboardId) {
    return (
      <DashboardDetail
        route={route}
        updateRoute={updateRoute}
        notify={notify}
        userId={userId}
      />
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
  return <DashboardList route={route} updateRoute={updateRoute} userId={userId} />;
}

function DashboardList({ route, updateRoute, userId }) {
  const [state, setState] = useState({ loading: true, error: "", data: null });
  const [filters, setFilters] = useState({ q: route.q, status: route.status });
  const generationRef = useRef(0);
  const controllerRef = useRef(null);

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

  const load = useCallback(async () => {
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const data = await dashboardApi.analysisDashboards(query, {
        signal: controller.signal,
      });
      if (generationRef.current === generation) {
        setState({ loading: false, error: "", data });
      }
    } catch (error) {
      if (generationRef.current === generation && error.name !== "AbortError") {
        setState((current) => ({ ...current, loading: false, error: error.message }));
      }
    }
  }, [query]);

  useEffect(() => {
    load();
    return () => {
      generationRef.current += 1;
      controllerRef.current?.abort();
    };
  }, [load]);

  const chooseResults = () => {
    const token = createDashboardSelection(userId);
    navigateHash("classification-results", { selection_token: token });
  };
  const totalPages = Math.max(Math.ceil((state.data?.total ?? 0) / route.pageSize), 1);

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
        <div>
          <MagnifyingGlass size={18} />
          <input
            aria-label="搜索分析看板"
            placeholder="搜索看板名称"
            value={filters.q}
            onChange={(event) => setFilters({ ...filters, q: event.target.value })}
          />
        </div>
        <select
          aria-label="看板状态"
          value={filters.status}
          onChange={(event) => setFilters({ ...filters, status: event.target.value })}
        >
          <option value="">全部状态</option>
          <option value="active">可用</option>
          <option value="archived">已归档</option>
        </select>
        <button
          className="primary-button"
          onClick={() => updateRoute({ ...filters, page: 1 })}
        >
          <FunnelSimple size={17} /> 筛选
        </button>
      </section>

      <section className="dashboard-list-card">
        {state.loading && !state.data && <InlineLoading label="正在读取分析看板…" />}
        {state.error && (
          <div className="dashboard-error" role="alert">
            <b>分析看板读取失败</b>
            <span>{state.error}</span>
            <button className="secondary-button" onClick={load}>
              重新加载
            </button>
          </div>
        )}
        {!state.loading && !state.error && state.data?.items?.length === 0 && (
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
        {state.data?.items?.length > 0 && !state.error && (
          <>
            <div
              className={`dashboard-list-table ${state.loading ? "is-loading" : ""}`}
            >
              <div className="dashboard-list-head" role="row">
                <span>状态</span>
                <span>看板名称</span>
                <span>当前版本</span>
                <span>数据范围</span>
                <span>记录数</span>
                <span>最近更新</span>
                <span>创建人</span>
                <span>操作</span>
              </div>
              {state.data.items.map((dashboard) => (
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
            <DashboardPagination
              page={route.page}
              pageSize={route.pageSize}
              total={state.data.total}
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

function DashboardRow({ dashboard, onOpen }) {
  const statusLabels = { active: "可用", archived: "已归档" };
  const summary = dashboard.summary ?? {};
  return (
    <article className="dashboard-list-row" role="row">
      <span className={`dashboard-status ${dashboard.status || "active"}`}>
        {statusLabels[dashboard.status] || dashboard.status || "可用"}
      </span>
      <div>
        <b>{dashboard.name || "未命名看板"}</b>
        <small>{dashboard.description || "未提供说明"}</small>
      </div>
      <b>v{dashboard.current_version || dashboard.version || 1}</b>
      <span>{Number(summary.listing_count || 0).toLocaleString()} 个 Listing</span>
      <span>{Number(summary.record_count || 0).toLocaleString()} 条</span>
      <span>{formatTime(dashboard.updated_at || dashboard.created_at)}</span>
      <span>{dashboard.created_by_name || "未提供"}</span>
      <button className="secondary-button compact-button" onClick={onOpen}>
        查看 <CaretRight size={15} />
      </button>
    </article>
  );
}
