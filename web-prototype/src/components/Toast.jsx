import { CheckCircle, WarningCircle, X } from "@phosphor-icons/react";

import { classNames } from "../lib/presentation";

/** @param {{message: import("react").ReactNode, tone?: string, onClose?: () => void}} props */
export function Toast({ message, tone, onClose }) {
  return (
    <div
      className={classNames("toast", tone)}
      role={tone === "error" ? "alert" : "status"}
      aria-live={tone === "error" ? "assertive" : "polite"}
    >
      {tone === "error" ? (
        <WarningCircle size={20} />
      ) : (
        <CheckCircle size={20} weight="fill" />
      )}
      <span>{message}</span>
      {tone === "error" && onClose && (
        <button
          type="button"
          className="icon-button toast-close"
          aria-label="关闭错误提示"
          onClick={onClose}
        >
          <X size={16} />
        </button>
      )}
    </div>
  );
}
