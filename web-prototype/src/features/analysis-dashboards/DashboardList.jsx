import { useDataRefresh } from "../../hooks/useDataRefresh";
import { MANAGED_REFRESH_OPTIONS } from "../../shared/refreshPolicy";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLoadingHeight } from "../../hooks/useLoadingHeight";
import { ChartBar, FunnelSimple, MagnifyingGlass } from "@phosphor-icons/react";
import Button from "antd/es/button";
import Input from "antd/es/input";
import useSWR from "swr";
import { navigateHash } from "../../app/hashRouter";
import { Pagination } from "../../components/Pagination";
import { EmptyState, InlineLoading, PageHeading } from "../../components/SharedUi";
import { dashboardApi } from "../../shared/api/dashboardApi";
import { errorStatus } from "../../shared/api/requestErrors";
import { serverStateKeys } from "../../shared/serverState";
import { createDashboardSelection } from "./dashboardSelectionStorage";
import { DashboardRow } from "./DashboardRow";

/** @typedef {import("./analysisDashboardContracts").DashboardListItem} DashboardListItem */
/** @typedef {import("./analysisDashboardContracts").DashboardListPage} DashboardListPage */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").UpdateDashboardRoute} UpdateDashboardRoute */
/** @typedef {{route: DashboardRoute, updateRoute: UpdateDashboardRoute, userId: string}} DashboardListProps */
/** @typedef {Pick<DashboardListProps, "route" | "updateRoute"> & ReturnType<typeof useDashboardList>} DashboardListContext */

/** @param {Pick<DashboardListProps, "route">} props */
function useDashboardList({ route }) {
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
    { ...MANAGED_REFRESH_OPTIONS, keepPreviousData: true },
  );
  useDataRefresh(() => mutate(), {
    loading: isLoading || isValidating,
    identity: JSON.stringify(query),
  });
  const message =
    error instanceof Error ? error.message : error ? "分析看板读取失败" : "";
  const load = () => mutate();

  const dashboardData = /** @type {DashboardListPage | undefined} */ (
    [401, 403].includes(Number(errorStatus(error))) ? undefined : data
  );
  const totalPages = Math.max(
    Math.ceil((dashboardData?.total ?? 0) / route.pageSize),
    1,
  );

  return {
    filters,
    setFilters,
    isLoading,
    isValidating,
    message,
    load,
    dashboardData,
    totalPages,
  };
}

/** @param {DashboardListProps} props */
export function DashboardList({ route, updateRoute, userId }) {
  const state = useDashboardList({ route });
  const chooseResults = () => {
    const token = createDashboardSelection(userId);
    navigateHash("classification-results", { selection_token: token });
  };

  const context = { route, updateRoute, ...state };
  return (
    <div className="standard-page analysis-dashboard-page">
      <PageHeading
        title="分析看板"
        action={
          <button className="primary-button" onClick={chooseResults}>
            <ChartBar size={18} /> 选择分类结果
          </button>
        }
      />

      <DashboardListFilters {...context} />

      <DashboardListResults {...context} />
    </div>
  );
}

/** @param {DashboardListContext} context */
function DashboardListFilters({ filters, setFilters, updateRoute }) {
  return (
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
          <option value="deleted">已删除</option>
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
  );
}

/** @param {DashboardListContext} context */
function DashboardListResults(context) {
  const { isLoading, dashboardData, message, load, route, updateRoute } = context;
  const regionRef = useRef(/** @type {HTMLElement | null} */ (null));
  useLoadingHeight(isLoading || context.isValidating, regionRef);
  return (
    <section
      ref={regionRef}
      className="dashboard-list-card loading-region"
      aria-busy={context.isValidating}
    >
      {isLoading && !dashboardData && (
        <InlineLoading scope="page" label="正在读取分析看板…" />
      )}
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
      {!isLoading && !message && dashboardData?.items.length === 0 && (
        <EmptyState
          icon={ChartBar}
          title={route.q || route.status ? "没有符合条件的看板" : "还没有分析看板"}
          action={
            route.q || route.status ? (
              <button
                className="secondary-button"
                onClick={() => updateRoute({ q: "", status: "", page: 1 })}
              >
                清除筛选
              </button>
            ) : undefined
          }
          description={
            route.q || route.status
              ? "调整筛选条件后重新查询。"
              : "先选择已发布的分类结果版本生成第一份看板。"
          }
        />
      )}
      {dashboardData && dashboardData.items.length > 0 && (
        <DashboardListTable {...context} dashboardData={dashboardData} />
      )}
    </section>
  );
}

/** @param {DashboardListContext & {dashboardData: DashboardListPage}} context */
function DashboardListTable({
  dashboardData,
  isValidating,
  route,
  updateRoute,
  totalPages,
}) {
  return (
    <>
      <div
        className={`dashboard-list-table${dashboardData.items.some((dashboard) => dashboard.deleted_at) ? " has-deleted" : ""}`}
        role="table"
        aria-label="分析看板列表"
        aria-busy={isValidating}
      >
        <div className="dashboard-list-head" role="row">
          <span role="columnheader">状态</span>
          <span role="columnheader">看板名称</span>
          <span role="columnheader">当前版本</span>
          <span role="columnheader">数据范围</span>
          <span role="columnheader">评论数</span>
          <span role="columnheader">最近更新</span>
          <span role="columnheader">创建人</span>
          <span role="columnheader">操作</span>
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
                reasonPage: 0,
                subject: "",
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
  );
}
