import { useEffect, useId, useRef, useState } from "react";
import { CalendarBlank } from "@phosphor-icons/react";
import { filterOptions } from "./returnReasonInsightPresentation";
/** @typedef {ReturnType<typeof import("./analysisContextPresentation").analysisContextTerms>} AnalysisContextTerms */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").InsightDateRange} InsightDateRange */
/** @typedef {import("./analysisDashboardContracts").InsightFilterOptions} InsightFilterOptions */
/** @typedef {{route: DashboardRoute, dateRange: InsightDateRange, options: InsightFilterOptions, terms: AnalysisContextTerms, ready?: boolean, onUpdateFilters: (changes: Partial<DashboardRoute>) => void}} SummaryFilterProps */

/** @param {Pick<SummaryFilterProps, "route" | "dateRange" | "onUpdateFilters">} props */
function DateFilter({ route, dateRange, onUpdateFilters }) {
  const from = route.dateFrom || dateRange.date_from || "";
  const to = route.dateTo || dateRange.date_to || "";
  const [draft, setDraft] = useState({ from, to });
  const [invalid, setInvalid] = useState(false);
  const errorId = useId();
  const fieldRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  useEffect(() => {
    setDraft({ from, to });
    setInvalid(false);
  }, [from, to]);
  const apply = () => {
    const fields = Array.from(fieldRef.current?.querySelectorAll("input") || []);
    // 复用原生日期约束；不把未完成、倒置或越界的草稿发送给看板。
    if (fields.some((field) => !field.value || !field.validity.valid)) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    if (draft.from !== from || draft.to !== to) {
      onUpdateFilters({ dateFrom: draft.from, dateTo: draft.to, problem: "" });
    }
  };
  return (
    <div
      className="return-insight-date-filter"
      ref={fieldRef}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) apply();
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          apply();
        }
      }}
    >
      <span>时间</span>
      <div>
        <CalendarBlank size={17} />
        <input
          aria-label="开始日期"
          type="date"
          value={draft.from}
          min={dateRange.date_from || undefined}
          max={draft.to || dateRange.date_to || undefined}
          aria-invalid={invalid}
          aria-describedby={invalid ? errorId : undefined}
          onChange={(event) => setDraft({ ...draft, from: event.target.value })}
        />
        <i>至</i>
        <input
          aria-label="结束日期"
          type="date"
          value={draft.to}
          min={draft.from || dateRange.date_from || undefined}
          max={dateRange.date_to || undefined}
          aria-invalid={invalid}
          aria-describedby={invalid ? errorId : undefined}
          onChange={(event) => setDraft({ ...draft, to: event.target.value })}
        />
      </div>
      {invalid && (
        <span className="return-insight-date-error" id={errorId} role="alert">
          请填写完整日期，开始日期不能晚于结束日期，且须在数据范围内。
          当前图表仍使用上次有效范围：{from} 至 {to}。
        </span>
      )}
    </div>
  );
}

/** @param {Pick<SummaryFilterProps, "route" | "options" | "onUpdateFilters" | "ready">} props */
function ProductFilters({ route, options, onUpdateFilters, ready }) {
  return (
    <>
      <InsightSelect
        label="Listing"
        ready={ready}
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
        ready={ready}
        value={route.productName}
        values={options.product_names}
        allLabel="全部产品"
        onChange={(productName) =>
          onUpdateFilters({ productName, productSku: "", problem: "" })
        }
      />
      <InsightSelect
        label="SKU"
        ready={ready}
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
        ready={props.ready}
      />
    </section>
  );
}

/** @param {{label: string, value: string, values?: string[], allLabel: string, ready?: boolean, onChange: (value: string) => void}} props */
function InsightSelect({ label, value, values, allLabel, ready = true, onChange }) {
  const id = useId();
  const choices = filterOptions(values);
  const missing = Boolean(value && !choices.includes(value));
  const invalid = ready && Array.isArray(values) && missing;
  return (
    <div className="return-insight-select">
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        value={value}
        aria-invalid={invalid}
        aria-describedby={invalid ? `${id}-error` : undefined}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{allLabel}</option>
        {missing && (
          <option value={value} disabled>
            {value}
            {invalid ? "（不在当前范围）" : ""}
          </option>
        )}
        {choices.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
      {invalid && (
        <div id={`${id}-error`} className="return-insight-select-error" role="alert">
          当前{label}不在可选范围内。
          <button type="button" className="text-button" onClick={() => onChange("")}>
            清除{label}筛选
          </button>
        </div>
      )}
    </div>
  );
}
