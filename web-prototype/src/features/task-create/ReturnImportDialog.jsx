import { useState } from "react";
import { FileArrowUp } from "@phosphor-icons/react";

import { api } from "../../api";
import { Modal } from "../../components/SharedUi";
import { ImportError, ReturnImportReview } from "./ReturnImportReview";

/** @typedef {"analyze_only" | "create" | "append" | "replace"} ReturnImportMode */
/** @typedef {import("./taskCreateContracts").ReturnImportInspection} ReturnImportInspection */
/** @typedef {import("./taskCreateContracts").ReturnImportResult} ReturnImportResult */

/**
 * @param {{onClose: () => void, onDone: (result: ReturnImportResult) => void | Promise<void>, purpose?: "task" | "asset"}} props
 */
export function ReturnImportDialog({ onClose, onDone, purpose = "task" }) {
  const [file, setFile] = useState(/** @type {File | null} */ (null));
  const [inspection, setInspection] = useState(
    /** @type {ReturnImportInspection | null} */ (null),
  );
  const [mode, setMode] = useState(/** @type {ReturnImportMode} */ ("analyze_only"));
  const [datasetId, setDatasetId] = useState("");
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [checking, setChecking] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const inspect = async (event) => {
    event.preventDefault();
    if (!file) {
      setError("请选择 CSV 或 XLSX 文件");
      return;
    }
    setChecking(true);
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      const result = /** @type {ReturnImportInspection} */ (
        await api.inspectReturnImport(body)
      );
      const firstMatch = result.matches?.[0];
      setInspection(result);
      setDatasetId(firstMatch?.dataset_id ?? "");
      setName(result.suggested_name ?? "");
      setMode(
        purpose === "asset" ? (firstMatch ? "append" : "create") : "analyze_only",
      );
    } catch (requestError) {
      setError(
        importErrorMessage(
          requestError,
          "请确认 CSV 或 XLSX 格式正确，修正后重新选择文件并检查。",
        ),
      );
    } finally {
      setChecking(false);
    }
  };

  const submit = async () => {
    if (!inspection?.inspection_id) return;
    if (["append", "replace"].includes(mode) && !datasetId) {
      setError("请选择要更新的数据源");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await onDone(
        /** @type {ReturnImportResult} */ (
          await api.importReturns({
            inspection_id: inspection.inspection_id,
            mode,
            dataset_id: datasetId,
            name: name.trim(),
            change_note: note.trim(),
          })
        ),
      );
    } catch (requestError) {
      setError(importErrorMessage(requestError, "请检查导入方式和目标数据源后重试。"));
    } finally {
      setSubmitting(false);
    }
  };

  const matches = inspection?.matches ?? [];
  const availableModes = availableImportModes(purpose, matches.length);
  const duplicate = inspection?.duplicate;
  const missingStoreRows = Number(inspection?.quality?.missing_store_rows ?? 0);
  const submitLabel = importSubmitLabel(duplicate, mode);

  return (
    <Modal
      eyebrow={purpose === "asset" ? "用户反馈数据源" : "待分析数据"}
      title={purpose === "asset" ? "导入新批次" : "导入一批用户反馈"}
      className="return-import-modal"
      onClose={onClose}
    >
      {!inspection ? (
        <form className="return-import-form" onSubmit={inspect}>
          <p className="return-import-intro">
            {purpose === "asset"
              ? "选择文件后，系统会识别业务范围并判断是建立新数据源还是更新现有数据源。"
              : "先选择文件。系统会识别店铺/站点、检查重复内容，再让你决定如何使用。"}
          </p>
          <label className="file-drop return-import-file">
            <input
              type="file"
              accept=".csv,.xlsx"
              onChange={(event) => {
                const selectedFile = event.target.files?.[0] ?? null;
                event.target.value = "";
                setFile(selectedFile);
                setInspection(null);
                setError("");
              }}
            />
            <FileArrowUp size={27} />
            <b>{file?.name ?? "选择 CSV 或 XLSX 文件"}</b>
            <span>最大 200 MB；此时不会创建数据或修改当前版本</span>
          </label>
          {error && <ImportError message={error} />}
          <div className="modal-actions">
            <button type="button" className="secondary-button" onClick={onClose}>
              取消
            </button>
            <button className="primary-button" disabled={!file || checking}>
              {checking ? "正在识别…" : "检查文件"}
            </button>
          </div>
        </form>
      ) : (
        <ReturnImportReview
          inspection={inspection}
          selection={{
            mode,
            datasetId,
            name,
            note,
            availableModes,
            matches,
            duplicate,
            missingStoreRows,
            submitting,
            submitLabel,
            error,
          }}
          actions={{
            onClose,
            onSubmit: submit,
            setMode,
            setDatasetId,
            setName,
            setNote,
            onChangeFile: () => {
              setFile(null);
              setInspection(null);
              setError("");
            },
          }}
        />
      )}
    </Modal>
  );
}

/** @param {unknown} error @param {string} nextStep */
function importErrorMessage(error, nextStep) {
  const detail = error instanceof Error ? error.message.trim() : "";
  if (/failed to fetch|network\s*error|networkerror|load failed/i.test(detail)) {
    return `无法连接服务，${nextStep}`;
  }
  return detail ? `${detail} ${nextStep}` : nextStep;
}

/** @param {ReturnImportInspection["duplicate"]} duplicate @param {ReturnImportMode} mode */
function importSubmitLabel(duplicate, mode) {
  if (duplicate && mode === "analyze_only") return "使用已导入的数据";
  if (mode === "append") return "追加并选中完整数据";
  if (mode === "replace") return "替换并选中新快照";
  if (mode === "create") return "建立数据源并选中";
  return "导入并分析本批";
}

/** @param {"task" | "asset"} purpose @param {number} matchCount @returns {ReturnImportMode[]} */
function availableImportModes(purpose, matchCount) {
  if (purpose === "asset") return matchCount ? ["append", "replace"] : ["create"];
  return matchCount
    ? ["analyze_only", "append", "replace"]
    : ["analyze_only", "create"];
}
