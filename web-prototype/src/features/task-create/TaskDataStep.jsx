import { useEffect, useState } from "react";
import { Database, FileArrowUp, FolderOpen, UploadSimple } from "@phosphor-icons/react";
import { MysqlReturnImportForm } from "./MysqlReturnImportForm";

/** @typedef {import("./taskCreateContracts").DataVersion} DataVersion */
/** @typedef {import("./taskCreateContracts").MysqlFormState} MysqlFormState */
/** @typedef {import("./taskCreateContracts").TaskForm} TaskForm */
/** @typedef {import("./MysqlReturnImportForm").MysqlImportResult} MysqlImportResult */
/** @typedef {import("./MysqlReturnImportForm").MysqlReturnFormState} MysqlReturnFormState */
/** @typedef {readonly ["mysql" | "upload" | "existing", string, import("react").ElementType]} DataEntryOption */

/** @type {readonly DataEntryOption[]} */
const DATA_ENTRY_OPTIONS = [
  ["mysql", "数据库", Database],
  ["upload", "上传文件", FileArrowUp],
  ["existing", "已有数据", FolderOpen],
];

/**
 * @param {{form: TaskForm, onFormChange: (form: TaskForm) => void, returns: DataVersion[], selectedReturns?: DataVersion, dataEntryMode: "mysql" | "upload" | "existing", selectedDataLabel: string, onDataEntryModeChange: (mode: "mysql" | "upload" | "existing") => void, onSelectedDataLabelChange: (label: string) => void, onUploadReturns: () => void, mysqlDraft?: Partial<MysqlReturnFormState>, onMysqlDraftChange: (draft: MysqlReturnFormState) => void, onMysqlDone: (result: MysqlImportResult) => void | Promise<void>, onMysqlStateChange: (state: MysqlFormState) => void, onInvalidateMysql: () => void, busy: boolean, prepared: boolean, scopeLabel: string, children?: import("react").ReactNode}} props
 */

export function TaskDataStep({
  form,
  onFormChange,
  returns,
  selectedReturns,
  dataEntryMode,
  selectedDataLabel,
  onDataEntryModeChange,
  onSelectedDataLabelChange,
  onUploadReturns,
  mysqlDraft,
  onMysqlDraftChange,
  onMysqlDone,
  onMysqlStateChange,
  onInvalidateMysql,
  busy,
  prepared,
  scopeLabel,
  children,
}) {
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    if (!prepared) setExpanded(false);
  }, [prepared]);
  return (
    <section className="task-config-panel task-data-step" aria-label="选择分析数据">
      <div className="task-config-section">
        <header className="task-data-section-heading">
          <div>
            <h2>{prepared ? "分析数据" : "选择分析数据"}</h2>
            <p>{prepared ? scopeLabel : "选择数据来源，确定本次分析范围。"}</p>
          </div>
          {prepared && (
            <button
              type="button"
              className="text-button"
              disabled={busy}
              aria-expanded={expanded}
              aria-controls="task-source-controls"
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded ? "收起数据详情" : "查看或修改数据"}
            </button>
          )}
        </header>
        <div id="task-source-controls" hidden={prepared && !expanded}>
          <div className="task-data-entry-options" role="group" aria-label="数据来源">
            {DATA_ENTRY_OPTIONS.map(([mode, label, Icon]) => (
              <button
                key={mode}
                type="button"
                disabled={busy}
                className={dataEntryMode === mode ? "active" : undefined}
                aria-pressed={dataEntryMode === mode}
                onClick={() => onDataEntryModeChange(mode)}
              >
                <Icon size={17} />
                {label}
              </button>
            ))}
          </div>
          {dataEntryMode === "mysql" ? (
            <MysqlReturnImportForm
              draft={mysqlDraft}
              onDraftChange={onMysqlDraftChange}
              onDone={onMysqlDone}
              onStateChange={onMysqlStateChange}
              onInvalidate={onInvalidateMysql}
              prepared={prepared}
              disabled={busy}
            />
          ) : (
            <>
              {dataEntryMode === "upload" ? (
                <div className="task-upload-source">
                  <div>
                    <b>{selectedReturns?.dataset_name || "选择要分析的退货文件"}</b>
                    <small>
                      {selectedReturns
                        ? `${selectedDataLabel || "本次上传数据"} · ${selectedReturns.row_count.toLocaleString()} 条记录`
                        : "上传 CSV，系统会识别字段并检查数据。"}
                    </small>
                  </div>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={busy}
                    onClick={onUploadReturns}
                  >
                    <UploadSimple size={17} />
                    {selectedReturns ? "更换文件" : "选择文件"}
                  </button>
                </div>
              ) : (
                <div className="task-data-picker existing-source-picker">
                  <label className="task-config-choice">
                    已有数据源
                    <select
                      value={form.dataset_version_id}
                      disabled={busy}
                      onChange={(event) => {
                        onFormChange({
                          ...form,
                          dataset_version_id: event.target.value,
                        });
                        onSelectedDataLabelChange(
                          event.target.value ? "当前完整数据" : "",
                        );
                      }}
                    >
                      <option value="">请选择数据源</option>
                      {returns.map((item) => (
                        <option key={item.version_id} value={item.version_id}>
                          {item.dataset_name} · {item.row_count.toLocaleString()} 条记录
                        </option>
                      ))}
                    </select>
                  </label>
                  {!returns.length && (
                    <p className="return-import-intro">
                      还没有保存的数据，可以从数据库读取或上传文件。
                    </p>
                  )}
                </div>
              )}
            </>
          )}
        </div>
        {children}
      </div>
    </section>
  );
}
