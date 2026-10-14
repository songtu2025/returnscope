import { useState } from "react";

import { Modal } from "../../components/SharedUi";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskPayload} TaskPayload */
/** @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment */

/**
 * @param {{task: AnalysisTask, segment: TaskSegment, error: string, onClose: () => void, onSave: (payload: TaskPayload) => Promise<unknown>}} props
 */

export function SegmentRetryDialog({ task, segment, error, onClose, onSave }) {
  const [saving, setSaving] = useState(false);
  const isFailureRetry = segment.system_retry_available === true;
  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      await onSave({
        expected_revision: task.revision,
        reason: isFailureRetry ? "重试分析失败项" : "重试 Listing",
      });
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal
      title={
        isFailureRetry
          ? "重试分析失败项？"
          : `重试 ${segment.scope?.listing || segment.agent_family}`
      }
      onClose={onClose}
    >
      <form className="modal-form" onSubmit={submit}>
        <p className="form-hint">
          {isFailureRetry
            ? "仅重试分析失败项，保留成功结果。"
            : "按启动时的配置重新分析该 Listing。"}
        </p>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            取消
          </button>
          <button className="primary-button" disabled={saving}>
            {saving ? "正在提交…" : isFailureRetry ? "开始重试" : "确认重试片段"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
