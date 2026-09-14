import { Modal } from "../../components/SharedUi";
import { EFFORT_LABELS } from "../../constants";

export function ModelEditorDialog({
  busy,
  editorMode,
  modelDraft,
  onChange,
  onClose,
  onSave,
}) {
  if (!editorMode || !modelDraft) return null;
  return (
    <Modal
      eyebrow="模型列表"
      title={editorMode === "create" ? "添加模型" : "编辑模型"}
      onClose={onClose}
    >
      <form
        className="modal-form model-editor-form"
        onSubmit={(event) => {
          event.preventDefault();
          onSave();
        }}
      >
        <label>
          模型 ID
          <input
            value={modelDraft.model_key}
            disabled={editorMode === "edit"}
            maxLength="120"
            placeholder="例如 deepseek-reasoner"
            onChange={(event) =>
              onChange({
                ...modelDraft,
                model_key: event.target.value,
              })
            }
            required
          />
          <small>
            必须与接入方 /models 返回的 ID 完全一致；系统不会预置品牌模型名称。
          </small>
        </label>
        <label>
          显示名称
          <input
            value={modelDraft.display_name}
            maxLength="80"
            placeholder="留空则使用模型 ID"
            onChange={(event) =>
              onChange({
                ...modelDraft,
                display_name: event.target.value,
              })
            }
          />
        </label>
        <fieldset className="model-effort-selector">
          <legend>支持的推理强度</legend>
          <div>
            {["low", "medium", "high"].map((effort) => {
              const selected = modelDraft.supported_efforts.includes(effort);
              return (
                <button
                  type="button"
                  className={selected ? "active" : ""}
                  key={effort}
                  onClick={() =>
                    onChange({
                      ...modelDraft,
                      supported_efforts: selected
                        ? modelDraft.supported_efforts.filter((item) => item !== effort)
                        : [...modelDraft.supported_efforts, effort].sort(
                            (left, right) =>
                              ["low", "medium", "high"].indexOf(left) -
                              ["low", "medium", "high"].indexOf(right),
                          ),
                    })
                  }
                >
                  {EFFORT_LABELS[effort]}
                </button>
              );
            })}
          </div>
        </fieldset>
        <p className="form-hint">
          模型验证会使用当前接入最近保存的 Base URL 和 API 密钥发送最小请求。
        </p>
        <div className="modal-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={onClose}
            disabled={busy === "model-save"}
          >
            取消
          </button>
          <button className="primary-button" disabled={busy === "model-save"}>
            {busy === "model-save" ? "保存中…" : "保存模型"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
