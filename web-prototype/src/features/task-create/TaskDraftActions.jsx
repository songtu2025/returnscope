import { useState } from "react";

/** @param {{disabled: boolean, onDiscard: () => void}} props */
export function TaskDraftActions({ disabled, onDiscard }) {
  const [confirming, setConfirming] = useState(false);
  return confirming ? (
    <div className="modal-actions" role="group" aria-label="放弃任务创建确认">
      <span>清除本次创建设置并返回任务列表？</span>
      <button
        className="secondary-button"
        disabled={disabled}
        onClick={() => setConfirming(false)}
      >
        继续创建
      </button>
      <button className="danger-button" disabled={disabled} onClick={onDiscard}>
        确认放弃
      </button>
    </div>
  ) : (
    <button
      className="secondary-button"
      disabled={disabled}
      onClick={() => setConfirming(true)}
    >
      放弃本次创建
    </button>
  );
}
