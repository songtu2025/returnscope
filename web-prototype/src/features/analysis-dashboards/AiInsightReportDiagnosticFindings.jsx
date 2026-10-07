import { EvidenceLine } from "./AiInsightReportCommon";
/** @typedef {import("./analysisDashboardContracts").ReportFinding} ReportFinding */
/** @typedef {import("./analysisDashboardContracts").InsightEvidenceCatalog} InsightEvidenceCatalog */

/** @param {{diagnosticFinding?: ReportFinding}} props */
export function DiagnosticFindingIntro({ diagnosticFinding }) {
  if (!diagnosticFinding) return null;
  return (
    <div className="ai-report-editorial-intro">
      <p>
        <b>{diagnosticFinding.conclusion}</b>
      </p>
      <p>{diagnosticFinding.interpretation}</p>
    </div>
  );
}

/** @param {{diagnosticFinding?: ReportFinding, catalog: InsightEvidenceCatalog}} props */
export function DiagnosticFindingConclusion({ diagnosticFinding, catalog }) {
  return (
    <>
      {diagnosticFinding && (
        <div className="ai-report-implication">
          <span>这意味着</span>
          <p>{diagnosticFinding.implication}</p>
        </div>
      )}

      {diagnosticFinding && (
        <EvidenceLine ids={diagnosticFinding.evidence_ids} catalog={catalog} />
      )}
    </>
  );
}

/** @param {{otherFindings: ReportFinding[]}} props */
export function ReportAdditionalFindings({ otherFindings }) {
  if (!otherFindings.length) return null;
  return (
    <div className="ai-report-generated-findings">
      {otherFindings.map((finding) => (
        <article key={finding.id || finding.title}>
          <h4>{finding.title}</h4>
          <b>{finding.conclusion}</b>
          <p>{finding.interpretation}</p>
          <p>
            <b>业务含义：</b>
            {finding.implication}
          </p>
        </article>
      ))}
    </div>
  );
}
