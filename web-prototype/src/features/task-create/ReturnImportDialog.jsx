import { useState } from "react";
import { FileArrowUp } from "@phosphor-icons/react";

import { api } from "../../api";
import { Modal } from "../../components/SharedUi";
import { ImportError, ReturnImportReview } from "./ReturnImportReview";

/** @typedef {import("./taskCreateContracts").ReturnImportInspection} ReturnImportInspection */
/** @typedef {import("./taskCreateContracts").ReturnImportResult} ReturnImportResult */

/**
 * @param {{onClose: () => void, onDone: (result: ReturnImportResult) => void | Promise<void>}} props
 */
export function ReturnImportDialog({ onClose, onDone }) {
  const [file, setFile] = useState(/** @type {File | null} */ (null));
  const [inspection, setInspection] = useState(
    /** @type {ReturnImportInspection | null} */ (null),
  );
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
      setInspection(result);
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
    setSubmitting(true);
    setError("");
    try {
      await onDone(
        /** @type {ReturnImportResult} */ (
          await api.importReturns({
            inspection_id: inspection.inspection_id,
            mode: "analyze_only",
          })
        ),
      );
    } catch (requestError) {
      setError(importErrorMessage(requestError, "请重新检查文件后重试。"));
    } finally {
      setSubmitting(false);
    }
  };

  const duplicate = inspection?.duplicate;
  const missingStoreRows = Number(inspection?.quality?.missing_store_rows ?? 0);
  const submitLabel = duplicate ? "使用已导入的数据" : "导入并分析本批";

  return (
    <Modal
      eyebrow="待分析数据"
      title="导入一批用户反馈"
      className="return-import-modal"
      onClose={onClose}
    >
      {!inspection ? (
        <form className="return-import-form" onSubmit={inspect}>
          <p className="return-import-intro">
            选择文件后，系统会识别店铺/站点并检查重复内容。导入的数据仅用于分析任务。
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
            duplicate,
            missingStoreRows,
            submitting,
            submitLabel,
            error,
          }}
          actions={{
            onClose,
            onSubmit: submit,
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
