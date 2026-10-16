/** @param {{segments: import("./taskPlanContracts").TaskPlanSegment[], filters: {query: string, category: string, status: string}, onFilter: (filters: {query: string, category: string, status: string}) => void, ordering: boolean, onToggleOrder?: () => void, onResetOrder?: () => void, rangeSelection?: {total: number, filtered: boolean, onChange: (selected: boolean) => void}}} props */
export function TaskPlanTableToolbar({
  segments,
  filters,
  onFilter,
  ordering,
  onToggleOrder,
  onResetOrder,
  rangeSelection,
}) {
  const categories = [
    ...new Set(
      segments.flatMap((item) =>
        item.variants.map((variant) => `${variant.category_a} / ${variant.category_b}`),
      ),
    ),
  ];
  return (
    <div className="plan-table-toolbar">
      <label>
        搜索分组
        <input
          aria-label="搜索执行分组"
          placeholder="Listing、店铺或分类标准"
          value={filters.query}
          onChange={(event) => onFilter({ ...filters, query: event.target.value })}
        />
      </label>
      <label>
        品类
        <select
          aria-label="按分组品类筛选"
          value={filters.category}
          onChange={(event) => onFilter({ ...filters, category: event.target.value })}
        >
          <option value="">全部品类</option>
          {categories.map((item) => (
            <option key={item}>{item}</option>
          ))}
        </select>
      </label>
      <label>
        执行状态
        <select
          aria-label="按分组执行状态筛选"
          value={filters.status}
          onChange={(event) => onFilter({ ...filters, status: event.target.value })}
        >
          <option value="">全部状态</option>
          <option value="ready">可执行</option>
          <option value="blocked">阻断</option>
        </select>
      </label>
      <button
        type="button"
        className="text-button"
        disabled={!filters.query && !filters.category && !filters.status}
        onClick={() => onFilter({ query: "", category: "", status: "" })}
      >
        清除筛选
      </button>
      {onToggleOrder && (
        <button
          type="button"
          className="text-button"
          aria-pressed={ordering}
          onClick={onToggleOrder}
        >
          {ordering ? "完成顺序调整" : "调整执行顺序"}
        </button>
      )}
      {onResetOrder && (
        <button
          type="button"
          className="secondary-button compact-button"
          onClick={onResetOrder}
        >
          恢复全部默认顺序
        </button>
      )}
      {rangeSelection && (
        <div className="plan-range-actions" role="group" aria-label="跨页范围选择">
          <button
            type="button"
            className="text-button"
            disabled={!rangeSelection.total}
            onClick={() => rangeSelection.onChange(true)}
          >
            {rangeSelection.filtered ? "全部筛选结果参与" : "全部范围参与"}
          </button>
          <button
            type="button"
            className="text-button"
            disabled={!rangeSelection.total}
            onClick={() => rangeSelection.onChange(false)}
          >
            {rangeSelection.filtered ? "全部筛选结果不参与" : "全部范围不参与"}
          </button>
        </div>
      )}
    </div>
  );
}
