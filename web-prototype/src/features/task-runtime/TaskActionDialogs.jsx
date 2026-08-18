import { useState } from "react";
import { X } from "@phosphor-icons/react";

import { Modal } from "../../components/SharedUi";

export function SegmentRetryDialog({ task, segment, onClose, onSave }) {
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
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
        <label>
          重试原因
          <textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            maxLength="500"
            rows="3"
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

export function SegmentCancelDialog({ segment, onClose, onSave }) {
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
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
            maxLength="500"
            rows="3"
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

export function TaskRenameDialog({ task, onClose, onSave }) {
  const [title, setTitle] = useState(task.title);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

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
    <div
      className="modal-backdrop"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="修改任务名称"
      >
        <header>
          <div>
            <p className="eyebrow">协作修改</p>
            <h2>修改任务名称</h2>
          </div>
          <button onClick={onClose} aria-label="关闭">
            <X size={18} />
          </button>
        </header>
        <form className="modal-form" onSubmit={submit}>
          <label>
            任务名称
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength="120"
              required
              autoFocus
            />
          </label>
          <label>
            修改原因
            <textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              maxLength="500"
              rows="3"
              placeholder="说明为什么需要修改，供团队追溯"
              required
            />
          </label>
          <p className="form-hint">
            数据、模型与分析范围属于不可变运行快照；名称修改会记录操作人和修改前后内容。
          </p>
          <div className="modal-actions">
            <button type="button" className="secondary-button" onClick={onClose}>
              取消
            </button>
            <button className="primary-button" disabled={saving}>
              {saving ? "正在保存…" : "保存修改"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

export function TaskCancelDialog({ task, onClose, onSave }) {
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

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
            maxLength="500"
            rows="3"
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

export function TaskResumeDialog({ task, onClose, onSave }) {
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const restarting = task.status === "cancelled";

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
            maxLength="500"
            rows="3"
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
