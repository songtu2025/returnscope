import { useState } from "react";
import { UploadSimple, WarningCircle } from "@phosphor-icons/react";
import { api } from "../api";
import { Modal } from "./SharedUi";

export function DatasetUploadDialog({ dialog, onClose, onDone, storeOptions = [] }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [note, setNote] = useState("");
  const [file, setFile] = useState(null);
  const [defaultStore, setDefaultStore] = useState(
    storeOptions.length === 1 ? storeOptions[0] : "",
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const kind = dialog.mode === "create" ? dialog.kind : dialog.dataset.kind;

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
    if (kind === "returns" && defaultStore) {
      body.append("default_store", defaultStore);
    }
    try {
      let result;
      if (dialog.mode === "create") {
        body.append("name", name);
        body.append("kind", kind);
        body.append("description", description);
        result = await api.createDataset(body);
      } else {
        result = await api.addDatasetVersion(dialog.dataset.id, body);
      }
      await onDone(result);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={
        dialog.mode === "create"
          ? kind === "returns"
            ? "导入退货明细"
            : "导入产品信息"
          : `为 ${dialog.dataset.name} 创建新版本`
      }
      onClose={onClose}
    >
      <form className="modal-form" onSubmit={submit}>
        {dialog.mode === "create" && (
          <>
            <label>
              {kind === "returns" ? "退货明细名称" : "产品信息名称"}
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
                rows="2"
              />
            </label>
          </>
        )}
        <label className="file-drop">
          <input
            type="file"
            accept={kind === "returns" ? ".csv" : ".xlsx"}
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <UploadSimple size={25} />
          <b>{file?.name ?? `选择 ${kind === "returns" ? "CSV" : "XLSX"} 文件`}</b>
          <span>最大 200 MB，上传后自动检查必需字段</span>
        </label>
        {kind === "returns" && (
          <label>
            缺失店铺/站点时补充为（可选）
            <input
              value={defaultStore}
              onChange={(event) => setDefaultStore(event.target.value)}
              list="return-store-options"
              maxLength="100"
              placeholder="例如 SEEKWAY:US"
            />
            <small>仅填补空值，不会覆盖文件中已有的店铺/站点。</small>
            <datalist id="return-store-options">
              {storeOptions.map((store) => (
                <option value={store} key={store} />
              ))}
            </datalist>
          </label>
        )}
        <label>
          版本说明
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            maxLength="500"
            placeholder="必填：例如补充 8 月 1—7 日数据"
            required
          />
        </label>
        {error && (
          <div className="form-error">
            <WarningCircle size={17} />
            {error}
          </div>
        )}
        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            取消
          </button>
          <button className="primary-button" disabled={submitting}>
            {submitting ? "正在校验并上传…" : "创建不可变版本"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
