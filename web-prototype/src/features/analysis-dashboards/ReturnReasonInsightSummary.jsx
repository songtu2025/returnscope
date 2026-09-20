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
import { analysisContextTerms } from "./analysisContextPresentation";

/** @typedef {import("./analysisDashboardContracts").DashboardInsights} DashboardInsights */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").InsightDateRange} InsightDateRange */
/** @typedef {import("./analysisDashboardContracts").InsightFilterOptions} InsightFilterOptions */
/** @typedef {{route: DashboardRoute, data: DashboardInsights, dateRange: InsightDateRange, options: InsightFilterOptions, includedCount: number, pendingCount: number, statusCounts: Record<string, number> | null, loading: boolean, analysisContext: string, onUpdateFilters: (changes: Partial<DashboardRoute>) => void}} ReturnReasonInsightSummaryProps */

/** @param {ReturnReasonInsightSummaryProps} props */
export function ReturnReasonInsightSummary({
  route,
  data,
  dateRange,
  options,
  includedCount,
  pendingCount,
  statusCounts,
  loading,
  analysisContext,
  onUpdateFilters,
}) {
  const terms = analysisContextTerms(analysisContext);
  return (
    <>
      <section className="return-insight-filters" aria-label={terms.filterAria}>
        <label className="return-insight-date-filter">
          <span>时间</span>
          <div>
            <CalendarBlank size={17} />
            <input
              aria-label="开始日期"
              type="date"
              disabled={loading}
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
              disabled={loading}
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
          disabled={loading}
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
          disabled={loading}
          onChange={(productName) =>
            onUpdateFilters({ productName, productSku: "", problem: "" })
          }
        />
        <InsightSelect
          label="SKU"
          value={route.productSku}
          values={options.product_skus}
          allLabel="全部 SKU"
          disabled={loading}
          onChange={(productSku) => onUpdateFilters({ productSku, problem: "" })}
        />
      </section>

      <section className="return-insight-trust" aria-label="数据可信度">
        <div>
          <ShieldCheck size={19} weight="duotone" />
          <span>{terms.includedLabel}</span>
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
          同一{terms.recordUnit}可命中多个原因，占比之和可能超过 100%。
          {data.group_alignment === "unified-v1" && " 跨版本已统一一级分组。"}
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

/** @param {{label: string, value: string, values?: string[], allLabel: string, disabled: boolean, onChange: (value: string) => void}} props */
function InsightSelect({ label, value, values, allLabel, disabled, onChange }) {
  return (
    <label className="return-insight-select">
      <span>{label}</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      >
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
