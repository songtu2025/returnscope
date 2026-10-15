import { useRef } from "react";
import { FunnelSimple, MagnifyingGlass } from "@phosphor-icons/react";
import Button from "antd/es/button";
import Input from "antd/es/input";

const statusOptions = [
  { value: "", label: "全部状态" },
  { value: "active", label: "可用" },
  { value: "archived", label: "已归档" },
  { value: "deleted", label: "已删除" },
];

/** @typedef {{q: string, status: string}} Filters */
/** @param {{filters: Filters, setFilters: import("react").Dispatch<import("react").SetStateAction<Filters>>, route: Filters, updateRoute: import("./analysisDashboardContracts").UpdateDashboardRoute, clearFilters: () => void}} props */
export function DashboardListFilters({
  filters,
  setFilters,
  route,
  updateRoute,
  clearFilters,
}) {
  const composing = useRef(false);
  const applied = [
    route.q && `关键词：${route.q}`,
    route.status &&
      `看板状态：${statusOptions.find((option) => option.value === route.status)?.label || route.status}`,
  ].filter(Boolean);
  return (
    <form
      className="dashboard-list-filters"
      aria-label="分析看板筛选"
      onCompositionStart={() => {
        composing.current = true;
      }}
      onCompositionEnd={() => {
        composing.current = false;
      }}
      onKeyDownCapture={(event) => {
        if (
          event.key === "Enter" &&
          (composing.current || event.nativeEvent.isComposing || event.keyCode === 229)
        )
          event.preventDefault();
      }}
      onSubmit={(event) => {
        event.preventDefault();
        if (!composing.current) updateRoute({ ...filters, page: 1 });
      }}
    >
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
          {statusOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <div className="dashboard-filter-actions">
        <Button type="primary" icon={<FunnelSimple size={17} />} htmlType="submit">
          筛选
        </Button>
        <Button onClick={clearFilters}>清除筛选</Button>
      </div>
      {applied.length > 0 && (
        <div
          className="dashboard-applied-filters"
          role="status"
          aria-label="已生效看板筛选"
        >
          <b>已生效</b>
          {applied.map((label) => (
            <span key={label}>{label}</span>
          ))}
        </div>
      )}
    </form>
  );
}
