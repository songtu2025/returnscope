import { InlineLoading } from "../../components/SharedUi";
import { useMysqlReturnImport } from "./useMysqlReturnImport";
import { MysqlReturnReview } from "./MysqlReturnReview";
import "../../styles/mysql-return-import.css";

/** @param {import("./mysqlReturnContracts").MysqlReturnImportFormProps} props */
export function MysqlReturnImportForm(props) {
  const state = useMysqlReturnImport(props);
  const { prepared = false, disabled = false } = props;
  const { schema, loading, displayError, refreshSchema, importData } = state;
  return (
    <form
      id="mysql-prepare-form"
      onSubmit={importData}
      onKeyDown={(event) => {
        if (event.key === "Escape" && event.target instanceof Element) {
          const details = event.target.closest("details");
          if (details instanceof HTMLDetailsElement) {
            details.open = false;
            details.querySelector("summary")?.focus();
          }
        }
      }}
      className="mysql-return-import"
      aria-label="从数据库取数"
    >
      {loading && <InlineLoading label="正在连接数据库并读取字段…" />}
      {displayError && (
        <div className="form-error" role="alert">
          {displayError}
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
        <MysqlReturnReview
          state={state}
          schema={schema}
          disabled={disabled}
          prepared={prepared}
        />
      )}
    </form>
  );
}
