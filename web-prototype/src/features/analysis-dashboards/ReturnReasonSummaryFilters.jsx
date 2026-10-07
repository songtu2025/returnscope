import { CalendarBlank } from "@phosphor-icons/react";
import { filterOptions } from "./returnReasonInsightPresentation";
/** @typedef {ReturnType<typeof import("./analysisContextPresentation").analysisContextTerms>} AnalysisContextTerms */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").InsightDateRange} InsightDateRange */
/** @typedef {import("./analysisDashboardContracts").InsightFilterOptions} InsightFilterOptions */
/** @typedef {{route: DashboardRoute, dateRange: InsightDateRange, options: InsightFilterOptions, terms: AnalysisContextTerms, onUpdateFilters: (changes: Partial<DashboardRoute>) => void}} SummaryFilterProps */

/** @param {Pick<SummaryFilterProps, "route" | "dateRange" | "onUpdateFilters">} props */
function DateFilter({ route, dateRange, onUpdateFilters }) {
  return (
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
  );
}

/** @param {Pick<SummaryFilterProps, "route" | "options" | "onUpdateFilters">} props */
function ProductFilters({ route, options, onUpdateFilters }) {
  return (
    <>
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
    </>
  );
}

/** @param {SummaryFilterProps} props */
export function ReturnReasonSummaryFilters(props) {
  return (
    <section className="return-insight-filters" aria-label={props.terms.filterAria}>
      <DateFilter
        route={props.route}
        dateRange={props.dateRange}
        onUpdateFilters={props.onUpdateFilters}
      />
      <ProductFilters
        route={props.route}
        options={props.options}
        onUpdateFilters={props.onUpdateFilters}
      />
    </section>
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
