import { MysqlReturnFilters } from "./MysqlReturnFilters";
import { MysqlReturnMapping } from "./MysqlReturnMapping";
import { MysqlReturnPreview, MysqlPreviewPending } from "./MysqlReturnPreview";

/** @typedef {ReturnType<typeof import("./useMysqlReturnImport").useMysqlReturnImport>} MysqlImportState */

/** @param {{state: MysqlImportState, schema: import("./mysqlReturnContracts").ConfiguredMysqlSchema, disabled: boolean, prepared: boolean}} props */
export function MysqlReturnReview({ state, schema, disabled, prepared }) {
  const {
    preview,
    loading,
    mappingReady,
    invalidDateRange,
    error,
    setPreviewRevision,
  } = state;
  const showPending =
    !prepared && !preview && !loading && mappingReady && !invalidDateRange;
  return (
    <div className="return-import-review">
      <MysqlReturnFilters {...state} schema={schema} disabled={disabled} />
      {invalidDateRange && (
        <p className="form-error" role="alert">
          开始日期不能晚于结束日期，请调整日期范围。
        </p>
      )}
      <MysqlReturnMapping {...state} schema={schema} disabled={disabled} />
      {showPending && (
        <MysqlPreviewPending error={error} setPreviewRevision={setPreviewRevision} />
      )}
      {preview && (
        <MysqlReturnPreview preview={preview} schema={schema} prepared={prepared} />
      )}
      <p className="return-import-intro mysql-snapshot-note">
        {prepared
          ? "已保存本次数据。修改筛选条件后需重新准备。"
          : "准备分析时保存数据快照，最终范围以检查结果为准。"}
      </p>
    </div>
  );
}
