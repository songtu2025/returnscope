import { MysqlPreviewTable } from "./MysqlPreviewTable";

/** @typedef {ReturnType<typeof import("./useMysqlReturnImport").useMysqlReturnImport>} MysqlImportState */

/** @param {{preview: import("./mysqlReturnContracts").MysqlPreview, schema: import("./mysqlReturnContracts").ConfiguredMysqlSchema, prepared: boolean}} props */
export function MysqlReturnPreview({ preview, schema, prepared }) {
  return (
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
      {preview.row_count === 0 && <p>没有符合条件的用户反馈，请调整筛选条件。</p>}
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
  );
}

/** @param {Pick<MysqlImportState,"error"|"setPreviewRevision">} props */
export function MysqlPreviewPending({ error, setPreviewRevision }) {
  return (
    <div className="mysql-preview-empty" role="status">
      {error ? "暂时无法显示数据" : "正在读取符合条件的用户反馈…"}
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
  );
}
