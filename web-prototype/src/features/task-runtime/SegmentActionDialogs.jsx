import { useState } from "react";

import { Modal } from "../../components/SharedUi";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskPayload} TaskPayload */
/** @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment */

/**
 * @param {{task: AnalysisTask, segment: TaskSegment, error: string, onClose: () => void, onSave: (payload: TaskPayload) => Promise<unknown>}} props
 */

export function SegmentRetryDialog({ task, segment, error, onClose, onSave }) {
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      await onSave({ expected_revision: task.revision, reason });
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal
      eyebrow="片段异常处理"
      title={`重试 ${segment.agent_family}`}
      onClose={onClose}
    >
      <form className="modal-form" onSubmit={submit}>
        <p className="form-hint">
          将按当前任务快照重新排队片段“{segment.segment_key}”；未知品类不能直接重试。
        </p>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <label>
          重试原因
          <textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            maxLength={500}
            rows={3}
            placeholder="必填，说明异常原因与重试依据"
            required
            autoFocus
          />
        </label>
        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            取消
          </button>
          <button className="primary-button" disabled={saving || !reason.trim()}>
            {saving ? "正在提交…" : "确认重试片段"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/**
 * @param {{segment: TaskSegment, onClose: () => void, onSave: (note: string) => Promise<unknown>}} props
 */
export function SegmentCancelDialog({ segment, onClose, onSave }) {
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      await onSave(note);
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal
      eyebrow="Listing 任务控制"
      title={`取消 ${segment.scope?.listing || segment.segment_key}`}
      onClose={onClose}
    >
      <form className="modal-form" onSubmit={submit}>
        <p className="form-hint">
          已完成的 Listing 不受影响；当前 Listing
          的处理中间数据只用于检查点恢复，不会进入正式结果。
        </p>
        <label>
          取消原因
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            maxLength={500}
            rows={3}
            placeholder="必填，说明为什么取消这个 Listing"
            required
            autoFocus
          />
        </label>
        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            返回
          </button>
          <button className="danger-button" disabled={saving || !note.trim()}>
            {saving ? "正在提交…" : "确认取消 Listing"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
