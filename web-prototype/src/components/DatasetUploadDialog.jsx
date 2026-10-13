import { useState } from "react";
import { UploadSimple, WarningCircle } from "@phosphor-icons/react";
import { api } from "../api";
import { Modal } from "./SharedUi";

/** @typedef {{id: string, name: string, kind: string, current_version: number}} UploadDataset */
/** @typedef {{mode: "create", kind: string} | {mode: "update", dataset: UploadDataset}} UploadDialog */

/**
 * @param {{
 *   dialog: UploadDialog,
 *   onClose: () => void,
 *   onDone: (result: unknown) => void | Promise<void>,
 *   onConflict?: (dataset: import("../shared/api/dataManagementContracts").DatasetRecord) => void | Promise<void>,
 * }} props
 */
export function DatasetUploadDialog({ dialog, onClose, onDone, onConflict }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [note, setNote] = useState("");
  const [file, setFile] = useState(/** @type {File | null} */ (null));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(
    dialog.mode === "update" ? dialog.dataset.current_version : 0,
  );
  const [stale, setStale] = useState(false);
  const kind = dialog.mode === "create" ? dialog.kind : dialog.dataset.kind;

  const refreshCurrent = async () => {
    if (dialog.mode !== "update") return;
    const latest = await api.dataset(dialog.dataset.id, { include: "" });
    setRevision(latest.current_version);
    await onConflict?.(latest);
    setStale(false);
    setError("资料已更新，请核对后重试");
  };

  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const submit = async (event) => {
    event.preventDefault();
    if (!file) {
      setError("请选择文件");
      return;
    }
    setSubmitting(true);
    setError("");
    const body = new FormData();
    body.append("file", file);
    body.append("change_note", note);
    try {
      if (stale) {
        await refreshCurrent();
        return;
      }
      let result;
      if (dialog.mode === "create") {
        body.append("name", name);
        body.append("kind", kind);
        body.append("description", description);
        result = await api.createDataset(body);
      } else {
        body.append("expected_version", String(revision));
        result = await api.updateDatasetContent(dialog.dataset.id, body);
      }
      await onDone(result);
    } catch (requestError) {
      if (
        requestError instanceof Error &&
        "status" in requestError &&
        requestError.status === 409
      ) {
        setStale(true);
        try {
          await refreshCurrent();
        } catch {
          setError("资料刷新失败，请重试刷新");
        }
      } else {
        setError(requestError instanceof Error ? requestError.message : "上传失败");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={dialog.mode === "create" ? "导入产品信息" : `更新 ${dialog.dataset.name}`}
      onClose={onClose}
    >
      <form className="modal-form" onSubmit={submit}>
        {dialog.mode === "create" && (
          <>
            <label>
              产品信息名称
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
                autoFocus
              />
            </label>
            <label>
              说明
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                rows={2}
              />
            </label>
          </>
        )}
        <label className="file-drop">
          <input
            type="file"
            accept=".xlsx"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <UploadSimple size={25} />
          <b>{file?.name ?? "选择 XLSX 文件"}</b>
          <span>最大 200 MB，上传后自动检查必需字段</span>
        </label>

        <label>
          修改说明
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            maxLength={500}
            placeholder="必填：例如补充产品名称和品类"
            required
          />
        </label>
        {error && (
          <div className="form-error" role="alert">
            <WarningCircle size={17} />
            {error}
          </div>
        )}
        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            取消
          </button>
          <button className="primary-button" disabled={submitting}>
            {submitting
              ? "正在校验并上传…"
              : stale
                ? "刷新资料"
                : dialog.mode === "create"
                  ? "导入"
                  : "保存更新"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
