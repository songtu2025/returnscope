import { useEffect, useRef, useState } from "react";
import { CaretDown } from "@phosphor-icons/react";
import { datePresets } from "./mysqlReturnDates";

/** @typedef {ReturnType<typeof import("./useMysqlReturnImport").useMysqlReturnImport>} MysqlImportState */

/** @param {Pick<MysqlImportState,"busy"|"loading"|"form"|"update"|"invalidDateRange"> & {schema: import("./mysqlReturnContracts").ConfiguredMysqlSchema, disabled: boolean}} props */
export function MysqlReturnFilters({
  busy,
  disabled,
  loading,
  schema,
  form,
  update,
  invalidDateRange,
}) {
  const [skuOpen, setSkuOpen] = useState(false);
  const skuRef = useRef(/** @type {HTMLDetailsElement | null} */ (null));
  const dateRef = useRef(/** @type {HTMLDetailsElement | null} */ (null));
  const inputRef = useRef(/** @type {HTMLInputElement | null} */ (null));
  const filtersDisabled = busy === "import" || disabled || loading;

  useEffect(() => {
    if (!skuOpen) return undefined;
    if (dateRef.current) dateRef.current.open = false;
    inputRef.current?.focus();
    /** @param {PointerEvent} event */
    const closeOutside = (event) => {
      if (event.target instanceof Node && !skuRef.current?.contains(event.target)) {
        setSkuOpen(false);
      }
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [skuOpen]);

  const closeSku = () => {
    setSkuOpen(false);
    skuRef.current?.querySelector("summary")?.focus();
  };

  return (
    <fieldset
      disabled={filtersDisabled}
      className="mysql-filter-toolbar"
      aria-label="分析范围"
    >
      <label className="mysql-store-filter">
        店铺/站点
        {schema.stores ? (
          <select
            value={form.store}
            onChange={(event) => update({ store: event.target.value })}
          >
            <option value="">全部店铺/站点</option>
            {schema.stores.map((store) => (
              <option key={store} value={store}>
                {store}
              </option>
            ))}
          </select>
        ) : (
          <input
            value={form.store}
            maxLength={100}
            onChange={(event) => update({ store: event.target.value })}
          />
        )}
      </label>
      <details ref={dateRef} className="mysql-date-filter">
        <summary onClick={() => setSkuOpen(false)}>
          反馈日期{" "}
          <b>
            {form.date_from || "不限起始"} — {form.date_to || "不限结束"}
          </b>
        </summary>
        <div className="mysql-date-popover">
          <div className="mysql-date-presets" aria-label="快捷日期范围" role="group">
            {datePresets().map(({ label, date_from, date_to }) => (
              <button
                key={label}
                type="button"
                aria-pressed={form.date_from === date_from && form.date_to === date_to}
                onClick={(event) => {
                  update({ date_from, date_to });
                  const details = event.currentTarget.closest("details");
                  if (details instanceof HTMLDetailsElement) details.open = false;
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="mysql-date-range">
            <label>
              开始日期
              <input
                type="date"
                value={form.date_from}
                max={form.date_to || undefined}
                aria-invalid={invalidDateRange}
                onChange={(event) => update({ date_from: event.target.value })}
              />
            </label>
            <span aria-hidden="true">至</span>
            <label>
              结束日期
              <input
                type="date"
                value={form.date_to}
                min={form.date_from || undefined}
                aria-invalid={invalidDateRange}
                onChange={(event) => update({ date_to: event.target.value })}
              />
            </label>
          </div>
          <small>包含起止当天，留空则不限。</small>
          <button
            type="button"
            className="text-button"
            disabled={invalidDateRange}
            onClick={(event) => {
              const details = event.currentTarget.closest("details");
              if (details instanceof HTMLDetailsElement) details.open = false;
            }}
          >
            完成
          </button>
        </div>
      </details>
      <details
        ref={skuRef}
        open={skuOpen}
        className="mysql-more-filter"
        onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) setSkuOpen(false);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape" && skuOpen) {
            event.preventDefault();
            event.stopPropagation();
            closeSku();
          }
        }}
      >
        <summary
          aria-expanded={skuOpen}
          aria-controls="mysql-sku-popover"
          aria-disabled={filtersDisabled}
          title={form.sku ? `商品：${form.sku}` : "指定商品"}
          onClick={(event) => {
            event.preventDefault();
            if (!filtersDisabled) setSkuOpen((current) => !current);
          }}
        >
          <span>{form.sku ? `商品：${form.sku}` : "指定商品"}</span>
          <CaretDown size={14} aria-hidden="true" />
        </summary>
        <label id="mysql-sku-popover">
          SKU / MSKU（精确匹配）
          <input
            ref={inputRef}
            aria-label="SKU / MSKU（精确匹配）"
            aria-describedby="mysql-sku-hint"
            value={form.sku}
            maxLength={200}
            onChange={(event) => update({ sku: event.target.value })}
            onKeyDown={(event) => {
              if (event.key !== "Enter") return;
              // Enter 只结束商品输入，不提交取数表单；输入法确认时保留浮层。
              event.preventDefault();
              if (!event.nativeEvent.isComposing && event.nativeEvent.keyCode !== 229) {
                closeSku();
              }
            }}
          />
          <small id="mysql-sku-hint">仅分析指定商品，留空则分析全部商品。</small>
        </label>
      </details>
    </fieldset>
  );
}
