import { ConciseInsightBody } from "./ConciseInsightBody";
import { VerifiableInsightBody } from "./VerifiableInsightBody";
import { dashboardVersionNumber } from "./dashboardFields";
import { date, reportLabel } from "./AiInsightReportPresentation";
import { InsightReportVersionSelect } from "./AiInsightDecisionHeader";

/** @typedef {import("./analysisDashboardContracts").InsightReport} InsightReport */
/** @typedef {import("./analysisDashboardContracts").DashboardVersion} DashboardVersion */
/** @typedef {import("./analysisDashboardContracts").ReportTheme} ReportTheme */
/** @typedef {import("./analysisDashboardContracts").InsightEvidenceCatalog} InsightEvidenceCatalog */

/** @param {{theme: ReportTheme, catalog: InsightEvidenceCatalog}} props */
function ThemeChapter({ theme, catalog }) {
  const evidence = theme.evidence_ids.map((id) => catalog[id]).filter(Boolean);
  return (
    <section className="theme-report-chapter" aria-labelledby={theme.id}>
      <header>
        <span className={theme.priority === "P0" ? "high-priority" : ""}>
          {theme.priority}
        </span>
        <h3 id={theme.id}>{theme.title}</h3>
      </header>
      <h4>观察事实</h4>
      <ul>
        {theme.facts.map((fact) => (
          <li key={fact}>{fact}</li>
        ))}
      </ul>
      <h4>诊断</h4>
      <p>{theme.diagnosis}</p>
      <h4>待验证假设</h4>
      <p>{theme.hypothesis}</p>
      <h4>产品影响</h4>
      <p>{theme.impact}</p>
      <h4>行动</h4>
      <p>{theme.action}</p>
      <h4>验证指标</h4>
      <p>{theme.metric}</p>
      <details>
        <summary>查看证据（{evidence.length} 项）</summary>
        <dl>
          {theme.evidence_ids.map((id) =>
            catalog[id] ? (
              <div key={id}>
                <dt>{catalog[id].label}</dt>
                <dd>{catalog[id].value}</dd>
              </div>
            ) : null,
          )}
        </dl>
      </details>
    </section>
  );
}

/** @param {{report: InsightReport, reports: InsightReport[], version: DashboardVersion | null, onSelect: (reportId: string) => void}} props */
export function AiThemeInsightReport({ report, reports, version, onSelect }) {
  const content = report.content;
  if (
    !content ||
    !("report_type" in content) ||
    (content.report_type !== "theme_insight" &&
      content.report_type !== "concise_insight" &&
      content.report_type !== "verifiable_insight")
  ) {
    return <p role="status">报告内容暂不可用，请重新生成。</p>;
  }
  const source = report.evidence?.source;
  const versionNumber = report.dashboard_version_no || dashboardVersionNumber(version);
  const finishedAt = report.completed_at?.slice(0, 19).replace("T", " ");
  const dates = source?.date_range;
  const dateRange =
    dates?.date_from && dates.date_to
      ? `${date(dates.date_from)} 至 ${date(dates.date_to)}`
      : dates?.date_from || dates?.date_to
        ? date(dates?.date_from || dates?.date_to)
        : "--";
  return (
    <article className="theme-insight-report" aria-labelledby="theme-report-title">
      <header className="theme-report-masthead">
        <div>
          <p>AI 洞察报告 / {reportLabel(report)}</p>
          <h2 id="theme-report-title">{content.title}</h2>
          <dl>
            <div>
              <dt>数据版本</dt>
              <dd>{versionNumber ? `V${versionNumber}` : "--"}</dd>
            </div>
            <div>
              <dt>反馈日期</dt>
              <dd>{dateRange}</dd>
            </div>
            <div>
              <dt>生成时间</dt>
              <dd>{finishedAt ? `${finishedAt} UTC` : "--"}</dd>
            </div>
          </dl>
        </div>
        <InsightReportVersionSelect
          report={report}
          reports={reports}
          onSelect={onSelect}
          optionLabel={reportLabel}
        />
      </header>

      {content.report_type === "verifiable_insight" ? (
        <VerifiableInsightBody
          content={content}
          count={source?.included_record_count}
        />
      ) : content.report_type === "concise_insight" ? (
        <ConciseInsightBody
          content={content}
          catalog={report.evidence?.catalog ?? {}}
        />
      ) : (
        <>
          <section
            className="theme-report-summary"
            aria-labelledby="theme-report-summary"
          >
            <h3 id="theme-report-summary">当前产品判断</h3>
            {content.executive_summary.length ? (
              content.executive_summary.map((item) => (
                <p key={item.evidence_ids?.[0]}>
                  <strong>{item.title}。</strong> {item.statement}
                </p>
              ))
            ) : (
              <p>当前样本没有可追溯的主题线索。</p>
            )}
          </section>

          {content.themes.map((theme) => (
            <ThemeChapter
              key={theme.id}
              theme={theme}
              catalog={report.evidence?.catalog ?? {}}
            />
          ))}

          <section
            className="theme-report-boundaries"
            aria-labelledby="theme-report-boundaries"
          >
            <h3 id="theme-report-boundaries">数据边界</h3>
            <ul>
              {content.boundaries.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </section>
        </>
      )}
    </article>
  );
}
