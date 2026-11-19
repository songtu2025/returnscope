import { dashboardVersionNumber } from "./dashboardFields";
import { date, reportLabel } from "./AiInsightReportPresentation";
import { SemanticInsightArticle } from "./SemanticInsightArticle";
import { feedbackCount } from "./semanticInsightPresentation";

/** @typedef {import("./analysisDashboardContracts").InsightReport} InsightReport */
/** @typedef {import("./analysisDashboardContracts").SemanticInsightReportContent} SemanticInsightReportContent */
/** @typedef {import("./analysisDashboardContracts").DashboardVersion} DashboardVersion */
/** @typedef {{report: InsightReport, version: DashboardVersion | null, analysisContext: string}} SemanticReportProps */

/** @param {{content: SemanticInsightReportContent, source: import("./analysisDashboardContracts").InsightReportSource}} props */
function ReportScope({ content, source }) {
  const overview = content.overview;
  return (
    <section className="semantic-report-scope" aria-labelledby="report-scope-title">
      <h3 id="report-scope-title">本报告分析了什么</h3>
      <p>
        共纳入 <strong>{feedbackCount(overview.total)}</strong> 条反馈，标签覆盖率为{" "}
        <strong>{overview.label_coverage.toFixed(1)}%</strong>；其中正向{" "}
        {feedbackCount(overview.positive)} 条、负向 {feedbackCount(overview.negative)}{" "}
        条、 混合 {feedbackCount(overview.mixed)} 条、无明确评价{" "}
        {feedbackCount(overview.unclear)} 条。
      </p>
      {Number(source.pending_review_record_count || 0) > 0 ? (
        <p className="semantic-report-scope-note">
          另有 {feedbackCount(source.pending_review_record_count)}{" "}
          条反馈仍待复核，暂不作为确定性结论。
        </p>
      ) : null}
    </section>
  );
}

/** @param {{content: SemanticInsightReportContent, source: import("./analysisDashboardContracts").InsightReportSource}} props */
function ReportLimits({ content, source }) {
  const notes = [
    source.product_mapping?.status === "needs_review"
      ? source.product_mapping.note
      : "",
    source.text_quality?.status === "needs_review" ? source.text_quality.note : "",
    ...content.caveats,
  ].filter(Boolean);
  return (
    <section className="semantic-report-limits" aria-labelledby="report-limits-title">
      <h3 id="report-limits-title">数据边界</h3>
      <ul>
        {notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
    </section>
  );
}

/** @param {SemanticReportProps} props */
export function AiSemanticInsightReport({ report, version, analysisContext }) {
  const content = /** @type {SemanticInsightReportContent | undefined} */ (
    report.content &&
    "report_type" in report.content &&
    report.content.report_type === "semantic_insight"
      ? report.content
      : undefined
  );
  if (!content) return <p role="status">报告内容暂不可用，请重新生成。</p>;
  const source = report.evidence?.source ?? {};
  const catalog = report.evidence?.catalog ?? {};
  const finishedAt = report.completed_at?.slice(0, 19).replace("T", " ");
  const versionNumber = report.dashboard_version_no || dashboardVersionNumber(version);
  return (
    <article
      className="semantic-insight-report"
      aria-labelledby="semantic-insight-title"
    >
      <header className="semantic-report-header">
        <div>
          <span>AI 洞察报告 · {reportLabel(report)}</span>
          <h2 id="semantic-insight-title">{content.title}</h2>
          <p>
            数据版本 {versionNumber ? `V${versionNumber}` : "--"} · 数据范围{" "}
            {date(source.date_range?.date_from)}–{date(source.date_range?.date_to)} ·
            生成时间 {finishedAt ? `${finishedAt} UTC` : "--"}
          </p>
        </div>
      </header>

      <ReportScope content={content} source={source} />
      <section
        className="semantic-report-insights"
        aria-labelledby="report-insights-title"
      >
        <h3 id="report-insights-title">核心洞察</h3>
        {content.issues.length ? (
          content.issues.map((issue, index) => (
            <SemanticInsightArticle
              key={issue.id}
              index={index + 1}
              issue={issue}
              catalog={catalog}
              analysisContext={analysisContext}
            />
          ))
        ) : (
          <p className="semantic-report-empty">当前样本没有可追溯的洞察。</p>
        )}
      </section>

      <ReportLimits content={content} source={source} />
    </article>
  );
}
