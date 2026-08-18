import { useEffect } from "react";
import {
  ArrowClockwise,
  CheckCircle,
  ShieldCheck,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { STATUS_LABELS } from "../constants";
import { classNames } from "../lib/presentation";

export function PageHeading({ eyebrow, title, description, action }) {
  return (
    <header className="page-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <span>{description}</span>
      </div>
      {action && <div className="heading-action">{action}</div>}
    </header>
  );
}

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

export function InfoRow({ label, value }) {
  return (
    <div className="info-row">
      <span>{label}</span>
      <b>{value ?? "—"}</b>
    </div>
  );
}

export function Modal({
  eyebrow = "数据版本",
  title,
  description = "",
  className = "",
  onClose,
  children,
}) {
  useEffect(() => {
    const closeOnEscape = (event) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <section
        className={classNames("modal", className)}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header>
          <div>
            {eyebrow && <p className="eyebrow">{eyebrow}</p>}
            <h2>{title}</h2>
            {description && <span className="modal-description">{description}</span>}
          </div>
          <button type="button" onClick={onClose} aria-label="关闭">
            <X size={20} />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}

export function StatusPill({ status, label }) {
  return (
    <span className={classNames("status-pill", status)}>
      <i />
      {label ?? STATUS_LABELS[status] ?? status}
    </span>
  );
}

export function StatusBadge({ value }) {
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

export function Kpi({ label, value, note }) {
  return (
    <div className="kpi-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

export function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="empty-state">
      <Icon size={29} />
      <b>{title}</b>
      <span>{description}</span>
      {action}
    </div>
  );
}

export function InlineLoading({ label }) {
  return (
    <div className="inline-loading">
      <ArrowClockwise size={18} />
      {label}
    </div>
  );
}

export function Toast({ message, tone }) {
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
      {message}
    </div>
  );
}

export function SectionTitle({ number, title, description }) {
  return (
    <div className="section-title">
      <span>{number}</span>
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
    </div>
  );
}

export function SnapshotNotice({ text }) {
  return (
    <div className="snapshot-notice">
      <ShieldCheck size={20} />
      <span>{text}</span>
    </div>
  );
}

export function Confirmation({ icon: Icon, label, value, note }) {
  return (
    <div className="confirmation">
      <Icon size={22} />
      <span>{label}</span>
      <b>{value}</b>
      <small>{note}</small>
    </div>
  );
}
