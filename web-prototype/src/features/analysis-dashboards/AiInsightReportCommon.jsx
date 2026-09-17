import {
  ArrowsClockwise,
  CheckCircle,
  Clock,
  WarningCircle,
} from "@phosphor-icons/react";

import {
  evidenceItems,
  reportLabel,
  STAGE_LABELS,
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
  const running = report.status === "queued" || report.status === "running";
  const historicalFailure =
    report.status === "failed" && latestReport && latestReport.id !== report.id;
  return (
    <section className={`ai-report-runtime-state ${report.status}`} role="status">
      {running ? <Clock size={28} /> : <WarningCircle size={28} />}
      <div>
        <span>
          {historicalFailure ? "历史生成记录 · " : ""}
          {reportLabel(report)}
        </span>
        <h2>
          {running
            ? "AI 正在生成洞察报告"
            : historicalFailure
              ? "这是一次历史生成失败"
              : "本次报告生成失败"}
        </h2>
        <p>
          {running
            ? `${STAGE_LABELS[report.stage || ""] || "系统正在生成报告"}。可以离开当前页面，进度也会显示在首页。`
            : historicalFailure
              ? `这次生成没有发布，也不会影响当前的报告 V${latestReport.version_no}。`
              : report.error || "模型没有返回可用的结构化报告。"}
        </p>
        <small>
          {report.model_name || report.model_key} · {report.reasoning_effort} 推理强度
        </small>
      </div>
      {historicalFailure && (
        <button className="primary-button" onClick={() => onSelect(latestReport.id)}>
          <CheckCircle size={17} /> 查看最新报告
        </button>
      )}
      {running && latestReport && (
        <button className="secondary-button" onClick={() => onSelect(latestReport.id)}>
          查看已发布报告
        </button>
      )}
      {report.status === "failed" && !historicalFailure && (
        <button className="primary-button" onClick={onRetry}>
          <ArrowsClockwise size={17} /> 重试
        </button>
      )}
    </section>
  );
}
