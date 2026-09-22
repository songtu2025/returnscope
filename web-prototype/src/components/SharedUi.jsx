import { X } from "@phosphor-icons/react";
import Empty from "antd/es/empty";
import Spin from "antd/es/spin";
import { STATUS_LABELS } from "../constants";
import { useDialogFocus } from "../hooks/useDialogFocus";
import { classNames } from "../lib/presentation";
import { AntdProvider } from "./AntdProvider";

/**
 * @param {{
 *   eyebrow?: import("react").ReactNode,
 *   title: import("react").ReactNode,
 *   description: import("react").ReactNode,
 *   action?: import("react").ReactNode,
 *   titleRef?: import("react").Ref<HTMLHeadingElement>,
 * }} props
 */
export function PageHeading({ eyebrow, title, description, action, titleRef }) {
  return (
    <header className="page-heading">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1 ref={titleRef} tabIndex={titleRef ? -1 : undefined}>
          {title}
        </h1>
        <span>{description}</span>
      </div>
      {action && <div className="heading-action">{action}</div>}
    </header>
  );
}

/** @param {{title: import("react").ReactNode, note?: import("react").ReactNode, action?: import("react").ReactNode}} props */
export function CardHeading({ title, note, action }) {
  return (
    <div className="card-heading">
      <div>
        <h3>{title}</h3>
        {note && <p>{note}</p>}
      </div>
      {action}
    </div>
  );
}

/** @param {{label: import("react").ReactNode, value?: import("react").ReactNode}} props */
export function InfoRow({ label, value }) {
  return (
    <div className="info-row">
      <span>{label}</span>
      <b>{value ?? "—"}</b>
    </div>
  );
}

/**
 * @param {{
 *   eyebrow?: import("react").ReactNode,
 *   title: string,
 *   description?: import("react").ReactNode,
 *   className?: string,
 *   onClose: () => void,
 *   children: import("react").ReactNode,
 * }} props
 */
export function Modal({
  eyebrow = "数据版本",
  title,
  description = "",
  className = "",
  onClose,
  children,
}) {
  const { dialogRef, constrainFocus } = useDialogFocus({ open: true, onClose });

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <section
        ref={dialogRef}
        className={classNames("modal", className)}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onKeyDownCapture={constrainFocus}
      >
        <header>
          <div>
            {eyebrow && <p className="eyebrow">{eyebrow}</p>}
            <h2>{title}</h2>
            {description && <span className="modal-description">{description}</span>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            data-dialog-initial-focus
          >
            <X size={20} />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}

/** @param {{status: string, label?: import("react").ReactNode}} props */
export function StatusPill({ status, label }) {
  return (
    <span className={classNames("status-pill", status)}>
      <i />
      {label ?? /** @type {Record<string, string>} */ (STATUS_LABELS)[status] ?? status}
    </span>
  );
}

/** @param {{value: string}} props */
export function StatusBadge({ value }) {
  /** @type {Record<string, string>} */
  const labels = {
    AUTO_APPROVED: "自动通过",
    MANUAL_RESOLVED: "人工已复核",
    SECONDARY_REVIEW: "二次复核",
    MANUAL_REVIEW: "人工复核",
    UNKNOWN_SEMANTIC: "未知语义",
    MODEL_ERROR: "模型错误",
    NO_TEXT_EVIDENCE: "无文本",
  };
  return (
    <span className={classNames("status-badge", value?.toLowerCase())}>
      {labels[value] ?? value}
    </span>
  );
}

/**
 * @param {{
 *   icon: import("@phosphor-icons/react").Icon,
 *   title: import("react").ReactNode,
 *   description: import("react").ReactNode,
 *   action?: import("react").ReactNode,
 * }} props
 */
export function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <AntdProvider>
      <Empty
        className="empty-state"
        image={<Icon size={29} />}
        description={
          <div className="empty-state-copy">
            <b>{title}</b>
            <span>{description}</span>
          </div>
        }
      >
        {action}
      </Empty>
    </AntdProvider>
  );
}

/** @param {{label: import("react").ReactNode}} props */
export function InlineLoading({ label }) {
  return (
    <AntdProvider>
      <Spin className="inline-loading" size="small" description={label} />
    </AntdProvider>
  );
}

/** @param {{label: import("react").ReactNode, heading?: boolean}} props */
export function PageLoadingState({ label, heading = true }) {
  return (
    <section className="page-loading-state" aria-busy="true">
      {heading && (
        <header className="page-loading-heading" aria-hidden="true">
          <span className="page-loading-title" />
          <span className="page-loading-subtitle" />
        </header>
      )}
      <InlineLoading label={label} />
    </section>
  );
}
