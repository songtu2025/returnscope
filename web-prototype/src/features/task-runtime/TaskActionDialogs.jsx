import { useRef, useState } from "react";

import { Modal } from "../../components/SharedUi";
export { SegmentRetryDialog } from "./SegmentActionDialogs";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskPayload} TaskPayload */

/**
 * @param {{task: AnalysisTask, onClose: () => void, onSave: (payload: TaskPayload) => Promise<unknown>}} props
 */
export function TaskResumeDialog({ task, onClose, onSave }) {
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const close = () => {
    if (!savingRef.current) onClose();
  };
  const restarting = task.status === "cancelled";

  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const submit = async (event) => {
    event.preventDefault();
    if (savingRef.current) return;
    savingRef.current = true;
    setSaving(true);
    try {
      await onSave({ expected_revision: task.revision });
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  return (
    <Modal title={`${restarting ? "重新排队" : "继续"}“${task.title}”`} onClose={close}>
      <form className="modal-form" onSubmit={submit}>
        <p className="form-hint">
          已完成的 Listing 片段及结果不会重复运行；系统只继续已中止和尚未运行的片段。
        </p>
        <div className="modal-actions">
          <button
            type="button"
            className="secondary-button"
            disabled={saving}
            onClick={close}
          >
            返回
          </button>
          <button className="primary-button" disabled={saving}>
            {saving
              ? "正在提交…"
              : restarting
                ? "重新排队未完成片段"
                : "继续未完成片段"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
