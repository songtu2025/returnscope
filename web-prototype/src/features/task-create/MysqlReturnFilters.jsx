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
  return (
    <fieldset
      disabled={busy === "import" || disabled || loading}
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
      <details className="mysql-date-filter">
        <summary>
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
      <details className="mysql-more-filter">
        <summary>{form.sku ? `商品：${form.sku}` : "指定商品"}</summary>
        <label>
          SKU / MSKU（精确匹配）
          <input
            aria-label="SKU / MSKU（精确匹配）"
            aria-describedby="mysql-sku-hint"
            value={form.sku}
            maxLength={200}
            onChange={(event) => update({ sku: event.target.value })}
          />
          <small id="mysql-sku-hint">仅分析指定商品，留空则分析全部商品。</small>
        </label>
      </details>
    </fieldset>
  );
}
