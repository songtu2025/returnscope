import { useEffect, useRef, useState } from "react";

import { Modal } from "../../components/SharedUi";
export { SegmentCancelDialog, SegmentRetryDialog } from "./SegmentActionDialogs";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskPayload} TaskPayload */

/**
 * @param {{task: AnalysisTask, onClose: () => void, onSave: (payload: TaskPayload) => Promise<unknown>}} props
 */
export function TaskRenameDialog({ task, onClose, onSave }) {
  const [title, setTitle] = useState(task.title);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const titleRef = useRef(/** @type {HTMLInputElement | null} */ (null));
  const continueRef = useRef(/** @type {HTMLButtonElement | null} */ (null));
  useEffect(() => {
    (confirmClose ? continueRef : titleRef).current?.focus();
  }, [confirmClose]);
  const close = () => {
    if (saving) return;
    if (confirmClose) setConfirmClose(false);
    else if (title !== task.title || note) setConfirmClose(true);
    else onClose();
  };

  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      await onSave({ title, note, expected_revision: task.revision });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal eyebrow="协作修改" title="修改任务名称" onClose={close}>
      {confirmClose ? (
        <div className="modal-form">
          <p>尚未保存的名称和修改原因会丢失，是否放弃修改？</p>
          <div className="modal-actions">
            <button
              ref={continueRef}
              className="secondary-button"
              onClick={() => setConfirmClose(false)}
            >
              继续编辑
            </button>
            <button className="danger-button" onClick={onClose}>
              放弃修改并关闭
            </button>
          </div>
        </div>
      ) : (
        <form className="modal-form" onSubmit={submit}>
          <label>
            任务名称
            <input
              ref={titleRef}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={120}
              required
            />
          </label>
          <label>
            修改原因
            <textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              maxLength={500}
              rows={3}
              placeholder="说明为什么需要修改，供团队追溯"
              required
            />
          </label>
          <p className="form-hint">
            数据、模型与分析范围属于不可变运行快照；名称修改会记录操作人和修改前后内容。
          </p>
          <div className="modal-actions">
            <button type="button" className="secondary-button" onClick={close}>
              取消
            </button>
            <button className="primary-button" disabled={saving}>
              {saving ? "正在保存…" : "保存修改"}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

/**
 * @param {{task: AnalysisTask, onClose: () => void, onSave: (payload: TaskPayload) => Promise<unknown>}} props
 */
export function TaskCancelDialog({ task, onClose, onSave }) {
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      await onSave({ note, expected_revision: task.revision });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal eyebrow="任务控制" title={`取消“${task.title}”`} onClose={onClose}>
      <form className="modal-form" onSubmit={submit}>
        <p className="form-hint">
          当前片段会在安全点停止，等待片段不再执行；已完成的 Listing
          会保留并生成可查看、可下载的部分结果。
        </p>
        <label>
          取消原因
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            maxLength={500}
            rows={3}
            placeholder="必填，说明为什么取消任务"
            required
            autoFocus
          />
        </label>
        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            返回
          </button>
          <button className="danger-button" disabled={saving || !note.trim()}>
            {saving ? "正在提交…" : "确认取消任务"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/**
 * @param {{task: AnalysisTask, onClose: () => void, onSave: (payload: TaskPayload) => Promise<unknown>}} props
 */
export function TaskResumeDialog({ task, onClose, onSave }) {
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const restarting = task.status === "cancelled";

  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      await onSave({ note, expected_revision: task.revision });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      eyebrow="任务控制"
      title={`${restarting ? "重新排队" : "继续"}“${task.title}”`}
      onClose={onClose}
    >
      <form className="modal-form" onSubmit={submit}>
        <p className="form-hint">
          已完成的 Listing 片段及结果不会重复运行；系统只继续已中止和尚未运行的片段。
        </p>
        <label>
          {restarting ? "重新排队原因" : "继续执行原因"}
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            maxLength={500}
            rows={3}
            placeholder={`必填，说明为什么${restarting ? "重新排队" : "继续执行"}`}
            required
            autoFocus
          />
        </label>
        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            返回
          </button>
          <button className="primary-button" disabled={saving || !note.trim()}>
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
