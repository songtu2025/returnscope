import { Target, WarningCircle } from "@phosphor-icons/react";
/** @typedef {import("./analysisDashboardContracts").LegacyInsightReportContent} LegacyInsightReportContent */

/** @param {{content: LegacyInsightReportContent}} props */
export function ReportBoundarySection({ content }) {
  const caveats = content.caveats ?? [];
  return (
    <section className="ai-report-section ai-report-boundary" id="report-boundary">
      <div className="ai-report-open-questions">
        <Target size={20} />
        <b>仍需回答的问题</b>
        <ul>
          {(content.further_questions ?? []).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>
      {caveats.length > 0 && (
        <>
          <p className="ai-report-primary-caveat">
            <WarningCircle size={16} /> {caveats[0]}
          </p>
          {caveats.length > 1 && (
            <details className="ai-report-limitations">
              <summary>查看其余报告口径与限制</summary>
              <ul>
                {caveats.slice(1).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </section>
  );
}
