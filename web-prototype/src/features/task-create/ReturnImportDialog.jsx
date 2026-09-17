import { useState } from "react";
import {
  CheckCircle,
  FileArrowUp,
  Info,
  UploadSimple,
  WarningCircle,
} from "@phosphor-icons/react";

import { api } from "../../api";
import { Modal } from "../../components/SharedUi";

/** @typedef {"analyze_only" | "create" | "append" | "replace"} ReturnImportMode */
/** @typedef {import("./taskCreateContracts").ReturnImportInspection} ReturnImportInspection */
/** @typedef {import("./taskCreateContracts").ReturnImportResult} ReturnImportResult */

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
  /** @type {ReturnImportMode[]} */
  const availableModes =
    purpose === "asset"
      ? matches.length
        ? ["append", "replace"]
        : ["create"]
      : matches.length
        ? ["analyze_only", "append", "replace"]
        : ["analyze_only", "create"];
  const duplicate = inspection?.duplicate;
  const missingStoreRows = Number(inspection?.quality?.missing_store_rows ?? 0);
  const submitLabel =
    duplicate && mode === "analyze_only"
      ? "使用已导入的数据"
      : mode === "append"
        ? "追加并选中完整数据"
        : mode === "replace"
          ? "替换并选中新快照"
          : mode === "create"
            ? "建立数据源并选中"
            : "导入并分析本批";

  return (
    <Modal
      eyebrow={purpose === "asset" ? "退货数据源" : "待分析数据"}
      title={purpose === "asset" ? "导入新批次" : "导入一批退货明细"}
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
        <div className="return-import-review">
          <section className="return-import-detection" aria-label="文件识别结果">
            <header>
              <CheckCircle size={21} weight="fill" />
              <div>
                <b>文件检查完成</b>
                <span>{inspection.original_name}</span>
              </div>
              <button
                type="button"
                className="link-button"
                onClick={() => {
                  setFile(null);
                  setInspection(null);
                  setError("");
                }}
              >
                更换文件
              </button>
            </header>
            <dl>
              <div>
                <dt>识别的数据源</dt>
                <dd>{inspection.suggested_name}</dd>
              </div>
              <div>
                <dt>店铺/站点</dt>
                <dd>{inspection.stores?.join("、") || "未识别"}</dd>
              </div>
              <div>
                <dt>数据行数</dt>
                <dd>{Number(inspection.row_count).toLocaleString()} 行</dd>
              </div>
              <div>
                <dt>有效评论</dt>
                <dd>
                  {Number(inspection.quality?.valid_comment_rows ?? 0).toLocaleString()}{" "}
                  行
                </dd>
              </div>
            </dl>
          </section>

          {duplicate && (
            <div className="return-import-notice duplicate" role="status">
              <Info size={18} weight="fill" />
              <span>
                这份文件已经导入到“{duplicate.dataset_name}
                ”。选择“仅分析本批”时会直接复用， 不会再创建重复数据。
              </span>
            </div>
          )}

          {missingStoreRows > 0 && (
            <div className="return-import-notice warning" role="alert">
              <WarningCircle size={18} weight="fill" />
              <span>
                有 {missingStoreRows.toLocaleString()}{" "}
                行缺少店铺/站点。请修正文件后重新检查。
              </span>
            </div>
          )}

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

          {["append", "replace"].includes(mode) && (
            <label>
              目标数据源
              <select
                value={datasetId}
                onChange={(event) => setDatasetId(event.target.value)}
              >
                {matches.map((item) => (
                  <option key={item.dataset_id} value={item.dataset_id}>
                    {item.dataset_name} · 当前 {Number(item.row_count).toLocaleString()}{" "}
                    行
                  </option>
                ))}
              </select>
            </label>
          )}

          {mode === "create" && (
            <label>
              数据源名称
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                maxLength={100}
              />
            </label>
          )}

          {mode !== "analyze_only" && (
            <label>
              变更说明（可选）
              <input
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="说明这次为什么追加或替换数据"
                maxLength={500}
              />
            </label>
          )}

          {mode === "replace" && (
            <div className="return-import-notice warning">
              <WarningCircle size={18} weight="fill" />
              <span>
                替换会改变该数据源的当前数据；历史快照和已创建任务不会被修改。
              </span>
            </div>
          )}
          {error && <ImportError message={error} />}
          <div className="modal-actions">
            <button type="button" className="secondary-button" onClick={onClose}>
              取消
            </button>
            <button
              type="button"
              className="primary-button"
              onClick={submit}
              disabled={submitting || missingStoreRows > 0}
            >
              {submitting
                ? "正在处理…"
                : missingStoreRows > 0
                  ? "请先修正文件"
                  : submitLabel}
              {!submitting && <UploadSimple size={17} />}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}

/** @param {{message: string}} props */
function ImportError({ message }) {
  return (
    <div className="form-error">
      <WarningCircle size={17} />
      {message}
    </div>
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
