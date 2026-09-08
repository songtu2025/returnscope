import { Fragment, useEffect, useState } from "react";
import { api } from "../../api";
import { InlineLoading } from "../../components/SharedUi";
import "../../styles/mysql-return-import.css";

function datePresets() {
  const today = new Date();
  const year = today.getFullYear();
  const month = today.getMonth();
  const day = today.getDate();
  const format = (date) =>
    date
      ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
      : "";

  return [
    ["不限日期", null, null],
    ["近7天", new Date(year, month, day - 6), today],
    ["近30天", new Date(year, month, day - 29), today],
    ["本月至今", new Date(year, month, 1), today],
    ["上月", new Date(year, month - 1, 1), new Date(year, month, 0)],
  ].map(([label, start, end]) => ({
    label,
    date_from: format(start),
    date_to: format(end),
  }));
}

export function MysqlReturnImportForm({
  onDone,
  draft,
  onDraftChange,
  onStateChange,
  onInvalidate,
  prepared = false,
  disabled = false,
}) {
  const [schema, setSchema] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [preview, setPreview] = useState(null);
  const [schemaRevision, setSchemaRevision] = useState(0);
  const [previewRevision, setPreviewRevision] = useState(0);
  const [form, setForm] = useState({
    mapping: {},
    default_store: "",
    date_from: datePresets()[2].date_from,
    date_to: datePresets()[2].date_to,
    store: "",
    sku: "",
    ...draft,
  });

  useEffect(() => {
    const controller = new AbortController();
    api
      .mysqlReturnSchema({ signal: controller.signal, refresh: schemaRevision > 0 })
      .then((result) => {
        setSchema(result);
        setForm((current) => ({
          ...current,
          mapping: { ...result.mapping, ...current.mapping },
        }));
      })
      .catch((requestError) => {
        if (!controller.signal.aborted) setError(requestError.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [schemaRevision]);

  useEffect(() => {
    onDraftChange?.(form);
  }, [form, onDraftChange]);

  const refreshSchema = () => {
    onInvalidate?.();
    setPreview(null);
    setBusy("");
    setError("");
    setLoading(true);
    setSchemaRevision((current) => current + 1);
  };

  const update = (changes) => {
    onInvalidate?.();
    setBusy("");
    setForm((current) => ({ ...current, ...changes }));
    setPreview(null);
    setError("");
  };
  const importData = async (event) => {
    event.preventDefault();
    if (!canPrepare || busy || disabled) return;
    setBusy("import");
    setError("");
    try {
      await onDone(
        await api.importMysqlReturns({
          ...form,
          date_from: form.date_from || null,
          date_to: form.date_to || null,
        }),
      );
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy("");
    }
  };
  const mappingReady =
    schema?.fields?.every((field) => !field.required || form.mapping[field.name]) &&
    (form.mapping["店铺/站点"] || form.default_store.trim());
  const invalidDateRange = Boolean(
    form.date_from && form.date_to && form.date_from > form.date_to,
  );

  const canPrepare = Boolean(
    !loading &&
    mappingReady &&
    !invalidDateRange &&
    preview?.row_count &&
    !preview.over_limit &&
    !preview.missing_store_rows,
  );

  useEffect(() => {
    onStateChange?.({ ready: canPrepare, busy, rowCount: preview?.row_count ?? 0 });
  }, [canPrepare, busy, preview, onStateChange]);

  useEffect(() => {
    if (prepared || loading || !schema?.configured || !mappingReady || invalidDateRange)
      return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setBusy("preview");
      setError("");
      try {
        const result = await api.previewMysqlReturns(
          {
            ...form,
            date_from: form.date_from || null,
            date_to: form.date_to || null,
          },
          { signal: controller.signal },
        );
        if (!controller.signal.aborted) setPreview(result);
      } catch (requestError) {
        if (!controller.signal.aborted) setError(requestError.message);
      } finally {
        if (!controller.signal.aborted) setBusy("");
      }
    }, 450);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [
    form,
    loading,
    schema,
    mappingReady,
    invalidDateRange,
    previewRevision,
    prepared,
  ]);

  return (
    <form
      id="mysql-prepare-form"
      onSubmit={importData}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          const details = event.target.closest("details");
          if (details) {
            details.open = false;
            details.querySelector("summary")?.focus();
          }
        }
      }}
      className="mysql-return-import"
      aria-label="从数据库取数"
    >
      {loading && <InlineLoading label="正在连接数据库并读取字段…" />}
      {error && (
        <div className="form-error" role="alert">
          {error}
          {!schema && (
            <button type="button" className="text-button" onClick={refreshSchema}>
              重新连接
            </button>
          )}
        </div>
      )}
      {schema?.configured === false && (
        <p className="return-import-intro" role="status">
          MySQL 数据源尚未配置。请联系维护人员完成连接配置后重新打开。
        </p>
      )}
      {schema?.configured && (
        <div className="return-import-review">
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
                退货日期{" "}
                <b>
                  {form.date_from || "不限起始"} — {form.date_to || "不限结束"}
                </b>
              </summary>
              <div className="mysql-date-popover">
                <div
                  className="mysql-date-presets"
                  aria-label="快捷日期范围"
                  role="group"
                >
                  {datePresets().map(({ label, date_from, date_to }) => (
                    <button
                      key={label}
                      type="button"
                      aria-pressed={
                        form.date_from === date_from && form.date_to === date_to
                      }
                      onClick={(event) => {
                        update({ date_from, date_to });
                        event.currentTarget.closest("details").open = false;
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
                    event.currentTarget.closest("details").open = false;
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
          {invalidDateRange && (
            <p className="form-error" role="alert">
              开始日期不能晚于结束日期，请调整日期范围。
            </p>
          )}
          <details className="task-advanced-settings" open={!mappingReady || undefined}>
            <summary>
              数据连接与字段{mappingReady ? " · 已就绪" : " · 需要补充"}
            </summary>
            <div className="task-advanced-body">
              <button
                type="button"
                className="secondary-button"
                disabled={busy === "import" || disabled || loading}
                onClick={refreshSchema}
              >
                刷新店铺与字段
              </button>
              <p className="return-import-intro">
                {schema.database} / {schema.table} · 单次最多{" "}
                {schema.max_rows.toLocaleString()} 行
              </p>
              <fieldset
                disabled={busy === "import" || disabled || loading}
                className="mysql-import-fields"
              >
                <legend>字段对应关系</legend>
                <p>系统按字段名称匹配，请核对业务含义。标有 * 的字段必须选择。</p>
                <div className="mysql-import-grid">
                  {schema.fields.map((field) => (
                    <label key={field.name}>
                      {field.label}
                      {field.required ? " *" : ""}
                      <select
                        aria-label={`${field.label}字段映射`}
                        value={form.mapping[field.name] ?? ""}
                        disabled={field.name === "店铺/站点" && Boolean(schema.stores)}
                        onChange={(event) =>
                          update({
                            mapping: {
                              ...form.mapping,
                              [field.name]: event.target.value,
                            },
                          })
                        }
                      >
                        <option value="">
                          {field.required ? "请选择字段" : "不映射"}
                        </option>
                        {schema.columns.map((column) => (
                          <option value={column.name} key={column.name}>
                            {column.label || column.name} ({column.type})
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                  {!form.mapping["店铺/站点"] && (
                    <label>
                      固定店铺/站点 *
                      <input
                        value={form.default_store}
                        maxLength={100}
                        placeholder="须与产品信息中的店铺/站点一致"
                        onChange={(event) =>
                          update({ default_store: event.target.value })
                        }
                      />
                    </label>
                  )}
                </div>
                <p>
                  未映射的 ASIN、FNSKU、产品名称会留空。
                  {!schema.stores &&
                    "固定店铺/站点只适用于整批数据属于同一店铺的情况。"}
                </p>
              </fieldset>
            </div>
          </details>
          {!prepared && !preview && !loading && mappingReady && !invalidDateRange && (
            <div className="mysql-preview-empty" role="status">
              {error ? "暂时无法显示数据" : "正在读取符合条件的退货数据…"}
              {error && (
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setPreviewRevision((value) => value + 1)}
                >
                  重试
                </button>
              )}
            </div>
          )}
          {preview && (
            <details
              open={!prepared}
              aria-label="数据库数据预览"
              className="mysql-import-preview"
            >
              <summary>
                <b role="status">
                  {preview.over_limit
                    ? `超过 ${schema.max_rows.toLocaleString()} 行，请缩小筛选范围`
                    : `匹配 ${preview.row_count.toLocaleString()} 行 · 展示前 ${preview.rows.length} 行`}
                </b>
                <span className="mysql-preview-caption">数据样例</span>
              </summary>
              {preview.row_count === 0 && (
                <p>没有符合条件的退货数据，请调整筛选条件。</p>
              )}
              {preview.missing_store_rows > 0 && (
                <p role="alert">
                  有 {preview.missing_store_rows.toLocaleString()}{" "}
                  行缺少店铺/站点映射，请选择已映射的店铺，或补齐源数据映射后重新预览。
                </p>
              )}
              {preview.rows.length > 0 && (
                <MysqlPreviewTable rows={preview.rows} fields={schema.fields} />
              )}
            </details>
          )}
          <p className="return-import-intro mysql-snapshot-note">
            {prepared
              ? "已保存本次数据。修改筛选条件后需重新准备。"
              : "准备分析时保存数据快照，最终范围以检查结果为准。"}
          </p>
        </div>
      )}
    </form>
  );
}

function MysqlPreviewTable({ rows, fields }) {
  const [page, setPage] = useState(0);
  const [expanded, setExpanded] = useState(null);
  const pageSize = 5;
  const start = page * pageSize;
  const end = Math.min(start + pageSize, rows.length);
  const changePage = (next) => {
    setPage(next);
    setExpanded(null);
  };

  return (
    <div className="mysql-preview-records">
      <table aria-label="退货数据样例" className="mysql-preview-table">
        <colgroup>
          <col className="mysql-preview-date-col" />
          <col className="mysql-preview-product-col" />
          <col className="mysql-preview-quantity-col" />
          <col className="mysql-preview-reason-col" />
          <col />
          <col className="mysql-preview-action-col" />
        </colgroup>
        <thead>
          <tr>
            {["退货日期", "商品 / 店铺", "数量", "退货原因", "客户评论", "操作"].map(
              (label) => (
                <th key={label} scope="col">
                  {label}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody>
          {rows.slice(start, end).map((row, offset) => {
            const index = start + offset;
            const isExpanded = expanded === index;
            const [date, time] = String(row["return-date"] || "—").split(/[T ]/);
            return (
              <Fragment key={index}>
                <tr>
                  <td className="mysql-preview-date">
                    <span>{date}</span>
                    {time && <small>{time}</small>}
                  </td>
                  <td>
                    <strong className="mysql-preview-excerpt">{row.sku || "—"}</strong>
                    <small className="mysql-preview-excerpt">
                      {row["店铺/站点"] || "未提供店铺"}
                    </small>
                  </td>
                  <td className="mysql-preview-quantity">{row.quantity ?? "—"}</td>
                  <td>
                    <span className="mysql-preview-excerpt">
                      {String(row.reason || "未提供").replaceAll("_", " ")}
                    </span>
                  </td>
                  <td>
                    <span className="mysql-preview-excerpt">
                      {row["customer-comments"] || "未填写评论"}
                    </span>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="mysql-preview-detail-button"
                      aria-label={`${isExpanded ? "收起" : "查看"}第${index + 1}条详情`}
                      aria-expanded={isExpanded}
                      aria-controls={
                        isExpanded ? `mysql-preview-detail-${index}` : undefined
                      }
                      onClick={() => setExpanded(isExpanded ? null : index)}
                    >
                      {isExpanded ? "收起" : "详情"}
                    </button>
                  </td>
                </tr>
                {isExpanded && (
                  <tr className="mysql-preview-detail-row">
                    <td colSpan={6}>
                      <dl
                        id={`mysql-preview-detail-${index}`}
                        aria-label={`第${index + 1}条完整记录`}
                      >
                        {fields.map((field) => (
                          <div
                            key={field.name}
                            className={
                              field.name === "customer-comments" ||
                              field.name === "product-name"
                                ? "mysql-preview-detail-wide"
                                : undefined
                            }
                          >
                            <dt>{field.label}</dt>
                            <dd>{String(row[field.name] ?? "") || "—"}</dd>
                          </div>
                        ))}
                      </dl>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      <div className="mysql-preview-pagination">
        <span>
          样例 {start + 1}–{end} / {rows.length} 条 · 导入范围不受分页影响
        </span>
        {rows.length > pageSize && (
          <div>
            <button
              type="button"
              className="secondary-button"
              disabled={page === 0}
              onClick={() => changePage(page - 1)}
            >
              上一页
            </button>
            <span>
              {page + 1} / {Math.ceil(rows.length / pageSize)}
            </span>
            <button
              type="button"
              className="secondary-button"
              disabled={end === rows.length}
              onClick={() => changePage(page + 1)}
            >
              下一页
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
