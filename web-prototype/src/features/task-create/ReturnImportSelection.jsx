/** @typedef {import("./ReturnImportDialog").ReturnImportMode} ReturnImportMode */
/** @typedef {import("./taskCreateContracts").ReturnImportInspection} ReturnImportInspection */
/** @typedef {{mode: ReturnImportMode, datasetId: string, name: string, note: string, availableModes: ReturnImportMode[], matches: NonNullable<ReturnImportInspection["matches"]>, duplicate: ReturnImportInspection["duplicate"], missingStoreRows: number, submitting: boolean, submitLabel: string, error: string}} ImportSelection */
/** @typedef {{onClose: () => void, onChangeFile: () => void, onSubmit: () => Promise<void>, setMode: (mode: ReturnImportMode) => void, setDatasetId: (id: string) => void, setName: (name: string) => void, setNote: (note: string) => void}} ImportActions */

/** @type {Record<ReturnImportMode, {title: string, description: string}>} */
const IMPORT_MODES = {
  analyze_only: {
    title: "仅分析本批",
    description: "不改变任何长期数据源；任务会固定使用这次上传的文件。",
  },
  create: {
    title: "建立长期数据源",
    description: "保存为一个新的业务数据源，后续任务可继续使用。",
  },
  append: {
    title: "追加到已有数据源",
    description: "跳过完全重复的记录，并分析合并后的当前完整数据。",
  },
  replace: {
    title: "替换当前数据",
    description: "上传文件成为新的当前完整数据；旧快照仍会保留。",
  },
};

/** @param {{selection: ImportSelection, actions: ImportActions}} props */
export function ReturnImportSelection({ selection, actions }) {
  const { mode, datasetId, name, note, availableModes, matches } = selection;
  return (
    <>
      <ImportModes
        mode={mode}
        availableModes={availableModes}
        setMode={actions.setMode}
      />

      {["append", "replace"].includes(mode) && (
        <ImportTargetSelect
          matches={matches}
          datasetId={datasetId}
          setDatasetId={actions.setDatasetId}
        />
      )}

      {mode === "create" && (
        <label>
          数据源名称
          <input
            value={name}
            onChange={(event) => actions.setName(event.target.value)}
            maxLength={100}
          />
        </label>
      )}

      {mode !== "analyze_only" && (
        <label>
          变更说明（可选）
          <input
            value={note}
            onChange={(event) => actions.setNote(event.target.value)}
            placeholder="说明这次为什么追加或替换数据"
            maxLength={500}
          />
        </label>
      )}
    </>
  );
}

/** @param {{mode: ReturnImportMode, availableModes: ReturnImportMode[], setMode: ImportActions["setMode"]}} props */
function ImportModes({ mode, availableModes, setMode }) {
  return (
    <fieldset className="return-import-mode-fieldset">
      <legend>这批数据如何进入系统？</legend>
      <div className="return-import-modes">
        {availableModes.map((value) => (
          <label className={mode === value ? "active" : ""} key={value}>
            <input
              type="radio"
              name="return-import-mode"
              value={value}
              checked={mode === value}
              onChange={() => setMode(value)}
            />
            <span>
              <b>{IMPORT_MODES[value].title}</b>
              <small>{IMPORT_MODES[value].description}</small>
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/** @param {{matches: ImportSelection["matches"], datasetId: string, setDatasetId: ImportActions["setDatasetId"]}} props */
function ImportTargetSelect({ matches, datasetId, setDatasetId }) {
  return (
    <label>
      目标数据源
      <select value={datasetId} onChange={(event) => setDatasetId(event.target.value)}>
        {matches.map((item) => (
          <option key={item.dataset_id} value={item.dataset_id}>
            {item.dataset_name} · 当前 {Number(item.row_count).toLocaleString()} 行
          </option>
        ))}
      </select>
    </label>
  );
}
