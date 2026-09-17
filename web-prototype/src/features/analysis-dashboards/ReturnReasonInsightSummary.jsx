import {
  CalendarBlank,
  ShieldCheck,
  TrendUp,
  WarningCircle,
} from "@phosphor-icons/react";
import { SEMANTIC_STATUS_LABELS } from "../classification-results/semanticResultPresentation";
import {
  COMMENT_STATUS_ORDER,
  filterOptions,
  formatPercent,
} from "./returnReasonInsightPresentation";

/** @typedef {import("./analysisDashboardContracts").DashboardInsights} DashboardInsights */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").InsightDateRange} InsightDateRange */
/** @typedef {import("./analysisDashboardContracts").InsightFilterOptions} InsightFilterOptions */
/** @typedef {{route: DashboardRoute, data: DashboardInsights, dateRange: InsightDateRange, options: InsightFilterOptions, includedCount: number, totalCount: number, pendingCount: number, statusCounts: Record<string, number> | null, onUpdateFilters: (changes: Partial<DashboardRoute>) => void}} ReturnReasonInsightSummaryProps */

/** @param {ReturnReasonInsightSummaryProps} props */
export function ReturnReasonInsightSummary({
  route,
  data,
  dateRange,
  options,
  includedCount,
  totalCount,
  pendingCount,
  statusCounts,
  onUpdateFilters,
}) {
  return (
    <>
      <section className="return-insight-filters" aria-label="退货原因洞察筛选">
        <label className="return-insight-date-filter">
          <span>时间</span>
          <div>
            <CalendarBlank size={17} />
            <input
              aria-label="开始日期"
              type="date"
              value={route.dateFrom || dateRange.date_from || ""}
              min={dateRange.date_from || undefined}
              max={route.dateTo || dateRange.date_to || undefined}
              onChange={(event) =>
                onUpdateFilters({ dateFrom: event.target.value, problem: "" })
              }
            />
            <i>至</i>
            <input
              aria-label="结束日期"
              type="date"
              value={route.dateTo || dateRange.date_to || ""}
              min={route.dateFrom || dateRange.date_from || undefined}
              max={dateRange.date_to || undefined}
              onChange={(event) =>
                onUpdateFilters({ dateTo: event.target.value, problem: "" })
              }
            />
          </div>
        </label>
        <InsightSelect
          label="Listing"
          value={route.listing}
          values={options.listings}
          allLabel="全部 Listing"
          onChange={(listing) =>
            onUpdateFilters({
              listing,
              productName: "",
              productSku: "",
              problem: "",
            })
          }
        />
        <InsightSelect
          label="产品"
          value={route.productName}
          values={options.product_names}
          allLabel="全部产品"
          onChange={(productName) =>
            onUpdateFilters({ productName, productSku: "", problem: "" })
          }
        />
        <InsightSelect
          label="SKU"
          value={route.productSku}
          values={options.product_skus}
          allLabel="全部 SKU"
          onChange={(productSku) => onUpdateFilters({ productSku, problem: "" })}
        />
      </section>

      <section className="return-insight-trust" aria-label="数据可信度">
        <div>
          <ShieldCheck size={19} weight="duotone" />
          <span>有效评论</span>
          <b>{includedCount.toLocaleString()} 条</b>
        </div>
        <div>
          <TrendUp size={18} />
          <span>问题标签覆盖</span>
          <b>{formatPercent(data.label_coverage)}</b>
        </div>
        <div className={pendingCount ? "warning" : ""}>
          <WarningCircle size={18} />
          <span>待复核</span>
          <b>{pendingCount.toLocaleString()} 条</b>
        </div>
        <p>
          当前洞察使用已确认与自动通过的数据；同一评论在每个分组内只计一次，多标签原因占比之和可能超过
          100%。
          {data.group_alignment === "unified-v1" &&
            " 跨版本已统一一级分组，具体标签保留原版本口径。"}
          <span>
            已分析 {includedCount.toLocaleString()}/{totalCount.toLocaleString()}{" "}
            条评论；事实数和事件数仅用于证据下钻
          </span>
        </p>
      </section>

      {statusCounts && (
        <section className="return-comment-statuses" aria-label="评论级结论分布">
          <header>
            <b>评论级结论</b>
            <span>互斥口径，每条评论只进入一种状态</span>
          </header>
          <div>
            {COMMENT_STATUS_ORDER.map((status) => (
              <article key={status} className={`is-${status.toLowerCase()}`}>
                <span>{SEMANTIC_STATUS_LABELS[status]}</span>
                <b>{Number(statusCounts[status] || 0).toLocaleString()}</b>
                <small>条评论</small>
              </article>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

/** @param {{label: string, value: string, values?: string[], allLabel: string, onChange: (value: string) => void}} props */
function InsightSelect({ label, value, values, allLabel, onChange }) {
  return (
    <label className="return-insight-select">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">{allLabel}</option>
        {filterOptions(values).map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
    </label>
  );
}
