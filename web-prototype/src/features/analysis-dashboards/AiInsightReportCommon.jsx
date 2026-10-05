import {
  ArrowsClockwise,
  CheckCircle,
  Clock,
  WarningCircle,
} from "@phosphor-icons/react";

import {
  evidenceItems,
  reportLabel,
  reportRuntimePresentation,
} from "./AiInsightReportPresentation";

/** @typedef {import("./analysisDashboardContracts").InsightEvidenceCatalog} InsightEvidenceCatalog */
/** @typedef {import("./analysisDashboardContracts").InsightReport} InsightReport */

/** @param {{ids?: string[], catalog: InsightEvidenceCatalog}} props */
export function EvidenceLine({ ids, catalog }) {
  const items = evidenceItems(ids, catalog);
  if (!items.length) return null;
  return (
    <aside className="ai-report-source-note" aria-label="本节数据证据">
      <span>数据证据 · {items.length} 项</span>
      <div className="ai-report-evidence-list" aria-label="结论证据">
        {items.map((item, index) => (
          <span key={`${item.label}-${index}`}>
            <b>{item.label}</b>
            <small>{item.value}</small>
          </span>
        ))}
      </div>
    </aside>
  );
}

/** @param {{number: string, title?: import("react").ReactNode, description?: import("react").ReactNode}} props */
export function SectionHeading({ number: sectionNumber, title, description }) {
  return (
    <header className="ai-report-section-heading">
      <span>{sectionNumber}</span>
      <div>
        <h3>{title}</h3>
        {description && <p>{description}</p>}
      </div>
    </header>
  );
}

/** @param {{report: InsightReport, latestReport: InsightReport | null, onRetry: () => void | Promise<void>, onSelect: (reportId: string) => void}} props */
export function ReportStatus({ report, latestReport, onRetry, onSelect }) {
  const status = reportRuntimePresentation(report, latestReport);
  return (
    <section className={`ai-report-runtime-state ${report.status}`} role="status">
      {status.kind === "running" ? <Clock size={28} /> : <WarningCircle size={28} />}
      <div>
        <span>
          {status.kind === "historical_failure" ? "历史生成记录 · " : ""}
          {reportLabel(report)}
        </span>
        <h2>{status.title}</h2>
        <p>{status.description}</p>
        <small>
          {report.model_name || report.model_key} · {report.reasoning_effort} 推理强度
        </small>
      </div>
      {status.kind === "historical_failure" && (
        <button
          className="primary-button"
          onClick={() => onSelect(status.latestReport.id)}
        >
          <CheckCircle size={17} /> 查看最新报告
        </button>
      )}
      {status.kind === "running" && latestReport && (
        <button className="secondary-button" onClick={() => onSelect(latestReport.id)}>
          查看已发布报告
        </button>
      )}
      {report.status === "failed" && status.kind !== "historical_failure" && (
        <button className="primary-button" onClick={onRetry}>
          <ArrowsClockwise size={17} /> 重试
        </button>
      )}
    </section>
  );
}
