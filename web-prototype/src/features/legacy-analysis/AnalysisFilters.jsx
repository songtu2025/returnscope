import { FunnelSimple, SlidersHorizontal } from "@phosphor-icons/react";
import { formatNumber } from "../../lib/presentation";

/** @typedef {import("../../shared/api/legacyAnalysisContracts").LegacyAnalysis} LegacyAnalysis */
/** @typedef {import("../../shared/api/legacyAnalysisContracts").AnalysisProblemLabel} AnalysisProblemLabel */
/** @typedef {Record<"start_date" | "end_date" | "category_a" | "category_b" | "listing" | "sku" | "asin" | "reason" | "status" | "problem_code" | "claim_relation", string>} AnalysisFilterValues */
/** @typedef {{analysis: LegacyAnalysis, filters: AnalysisFilterValues, filtersOpen: boolean, activeFilterCount: number, onReset: () => void, onToggle: () => void, onChange: (name: keyof AnalysisFilterValues, value: string) => void}} AnalysisFiltersProps */

/** @type {Array<{label: string, name: keyof AnalysisFilterValues, optionsKey: "listings" | "problem_labels" | "statuses" | "category_as" | "category_bs" | "reasons" | "skus" | "claim_relations"}>} */
const SELECT_FILTERS = [
  {
    label: "Listing",
    name: "listing",
    optionsKey: "listings",
  },
  {
    label: "问题标签",
    name: "problem_code",
    optionsKey: "problem_labels",
  },
  {
    label: "处理状态",
    name: "status",
    optionsKey: "statuses",
  },
  {
    label: "品类A",
    name: "category_a",
    optionsKey: "category_as",
  },
  {
    label: "品类B",
    name: "category_b",
    optionsKey: "category_bs",
  },
  {
    label: "Amazon 原因",
    name: "reason",
    optionsKey: "reasons",
  },
  {
    label: "SKU",
    name: "sku",
    optionsKey: "skus",
  },
  {
    label: "Listing 承诺关系",
    name: "claim_relation",
    optionsKey: "claim_relations",
  },
];

/** @param {{label: string, value: string, onChange: (value: string) => void} & Omit<import("react").InputHTMLAttributes<HTMLInputElement>, "value" | "onChange">} props */
function FilterInput({ label, value, onChange, ...props }) {
  return (
    <label className="analysis-filter-field">
      <span>{label}</span>
      <input
        {...props}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

/** @param {{label: string, value: string, options?: Array<string | AnalysisProblemLabel>, optionValue?: "code" | null, optionLabel?: "name" | null, onChange: (value: string) => void}} props */
function FilterSelect({
  label,
  value,
  options = [],
  optionValue = null,
  optionLabel = null,
  onChange,
}) {
  return (
    <label className="analysis-filter-field">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">全部</option>
        {options.map((option) => {
          const optionId =
            typeof option === "string"
              ? option
              : optionValue
                ? option[optionValue]
                : option.code;
          const optionName =
            typeof option === "string"
              ? option
              : optionLabel
                ? option[optionLabel]
                : option.name;
          return (
            <option key={optionId} value={optionId}>
              {optionName}
            </option>
          );
        })}
      </select>
    </label>
  );
}

/** @param {Pick<AnalysisFiltersProps, "analysis" | "filtersOpen" | "activeFilterCount" | "onReset" | "onToggle">} props */
function FilterHeader({ analysis, filtersOpen, activeFilterCount, onReset, onToggle }) {
  return (
    <header>
      <div>
        <FunnelSimple size={19} />
        <div>
          <b>分析筛选</b>
          <span>
            当前范围 {formatNumber(analysis.scope.filtered_records)} /{" "}
            {formatNumber(analysis.scope.total_records)} 条退货记录
          </span>
        </div>
      </div>
      <div>
        {activeFilterCount > 0 && (
          <button className="text-button" onClick={onReset}>
            重置筛选
          </button>
        )}
        <button
          className="secondary-button"
          onClick={onToggle}
          aria-expanded={filtersOpen}
        >
          <SlidersHorizontal size={17} />
          {filtersOpen
            ? "收起"
            : `展开${activeFilterCount ? `（${activeFilterCount}）` : ""}`}
        </button>
      </div>
    </header>
  );
}

/** @param {Pick<AnalysisFiltersProps, "analysis" | "filters" | "onChange">} props */
function DateFilters({ analysis, filters, onChange }) {
  return (
    <>
      <FilterInput
        label="开始日期"
        type="date"
        min={analysis.filters.date_min ?? undefined}
        max={analysis.filters.date_max ?? undefined}
        value={filters.start_date}
        onChange={(value) => onChange("start_date", value)}
      />
      <FilterInput
        label="结束日期"
        type="date"
        min={analysis.filters.date_min ?? undefined}
        max={analysis.filters.date_max ?? undefined}
        value={filters.end_date}
        onChange={(value) => onChange("end_date", value)}
      />
    </>
  );
}

/** @param {Pick<AnalysisFiltersProps, "analysis" | "filters" | "onChange">} props */
function SelectFilters({ analysis, filters, onChange }) {
  return SELECT_FILTERS.map((field) => (
    <FilterSelect
      key={field.name}
      label={field.label}
      value={filters[field.name]}
      options={analysis.filters[field.optionsKey]}
      optionValue={field.name === "problem_code" ? "code" : null}
      optionLabel={field.name === "problem_code" ? "name" : null}
      onChange={(value) => onChange(field.name, value)}
    />
  ));
}

/** @param {AnalysisFiltersProps} props */
export function AnalysisFilters({
  analysis,
  filters,
  filtersOpen,
  activeFilterCount,
  onReset,
  onToggle,
  onChange,
}) {
  return (
    <section className={`analysis-filter-panel ${filtersOpen ? "is-open" : ""}`}>
      <FilterHeader
        analysis={analysis}
        filtersOpen={filtersOpen}
        activeFilterCount={activeFilterCount}
        onReset={onReset}
        onToggle={onToggle}
      />
      {filtersOpen && (
        <div className="analysis-filter-grid">
          <DateFilters analysis={analysis} filters={filters} onChange={onChange} />
          <SelectFilters analysis={analysis} filters={filters} onChange={onChange} />
        </div>
      )}
    </section>
  );
}
