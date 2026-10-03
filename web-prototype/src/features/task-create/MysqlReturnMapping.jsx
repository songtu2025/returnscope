/** @typedef {ReturnType<typeof import("./useMysqlReturnImport").useMysqlReturnImport>} MysqlImportState */

/** @param {Pick<MysqlImportState,"busy"|"loading"|"form"|"update"|"mappingReady"|"refreshSchema"> & {schema: import("./mysqlReturnContracts").ConfiguredMysqlSchema, disabled: boolean}} props */
export function MysqlReturnMapping({
  busy,
  disabled,
  loading,
  schema,
  form,
  update,
  mappingReady,
  refreshSchema,
}) {
  return (
    <details className="task-advanced-settings" open={!mappingReady || undefined}>
      <summary>数据连接与字段{mappingReady ? " · 已就绪" : " · 需要补充"}</summary>
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
                  <option value="">{field.required ? "请选择字段" : "不映射"}</option>
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
                  onChange={(event) => update({ default_store: event.target.value })}
                />
              </label>
            )}
          </div>
          <p>
            未映射的 ASIN、FNSKU、产品名称会留空。
            {!schema.stores && "固定店铺/站点只适用于整批数据属于同一店铺的情况。"}
          </p>
        </fieldset>
      </div>
    </details>
  );
}
