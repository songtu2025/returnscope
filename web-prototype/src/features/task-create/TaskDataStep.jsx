import { useEffect, useState } from "react";
import { Database, FileArrowUp, UploadSimple } from "@phosphor-icons/react";
import { MysqlReturnImportForm } from "./MysqlReturnImportForm";

/** @typedef {import("./taskCreateContracts").DataVersion} DataVersion */
/** @typedef {import("./mysqlReturnContracts").MysqlFormState} MysqlFormState */
/** @typedef {import("./mysqlReturnContracts").MysqlImportResult} MysqlImportResult */
/** @typedef {import("./mysqlReturnContracts").MysqlReturnFormState} MysqlReturnFormState */
/** @typedef {readonly ["mysql" | "upload", string, import("react").ElementType]} DataEntryOption */

/** @type {readonly DataEntryOption[]} */
const DATA_ENTRY_OPTIONS = [
  ["mysql", "数据库", Database],
  ["upload", "上传文件", FileArrowUp],
];

/**
 * @typedef {{selectedReturns?: DataVersion, dataEntryMode: "mysql" | "upload", selectedDataLabel: string, onDataEntryModeChange: (mode: "mysql" | "upload") => void, onUploadReturns: () => void, mysqlDraft?: Partial<MysqlReturnFormState>, onMysqlDraftChange: (draft: MysqlReturnFormState) => void, onMysqlDone: (result: MysqlImportResult) => void | Promise<void>, onMysqlStateChange: (state: MysqlFormState) => void, onInvalidateMysql: () => void, busy: boolean, prepared: boolean, scopeLabel: string, children?: import("react").ReactNode}} TaskDataStepProps
 */

/** @param {TaskDataStepProps} props */
export function TaskDataStep({
  selectedReturns,
  dataEntryMode,
  selectedDataLabel,
  onDataEntryModeChange,
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
            {prepared && <p>{scopeLabel}</p>}
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
            <TaskUploadSource
              selectedReturns={selectedReturns}
              selectedDataLabel={selectedDataLabel}
              onUploadReturns={onUploadReturns}
              busy={busy}
            />
          )}
        </div>
        {children}
      </div>
    </section>
  );
}

/** @param {Pick<TaskDataStepProps, "selectedReturns" | "selectedDataLabel" | "onUploadReturns" | "busy">} props */
function TaskUploadSource({
  selectedReturns,
  selectedDataLabel,
  onUploadReturns,
  busy,
}) {
  return (
    <div className="task-upload-source">
      <div>
        <b>{selectedReturns?.dataset_name || "选择要分析的用户反馈文件"}</b>
        <small>
          {selectedReturns
            ? `${selectedDataLabel || "本次上传数据"} · ${selectedReturns.row_count.toLocaleString()} 条记录`
            : "上传 CSV 或 XLSX，系统会识别字段并检查数据。"}
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
  );
}
