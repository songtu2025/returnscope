import { analysisContextTerms } from "./analysisContextPresentation";
import { DecisionEvidenceDetails } from "./AiInsightDecisionEvidence";
import { insightKindLabels, issueMetricSummary } from "./semanticInsightPresentation";

/** @typedef {import("./analysisDashboardContracts").SemanticInsightIssue} SemanticInsightIssue */
/** @typedef {import("./analysisDashboardContracts").InsightEvidenceCatalog} InsightEvidenceCatalog */

const locationPattern = /\.(hotspot|variant)\.1$/;

/** @param {{issue: SemanticInsightIssue, catalog: InsightEvidenceCatalog}} props */
function IssueLocation({ issue, catalog }) {
  const locations = issue.evidence_ids
    .filter((id) => locationPattern.test(id) && catalog[id])
    .map((id) => catalog[id]);
  if (!locations.length) return null;
  return (
    <p className="semantic-report-location">
      <strong>主要定位：</strong>
      {locations.map((item) => `${item.label} ${item.value}`).join("；")}
    </p>
  );
}

/** @param {{issue: SemanticInsightIssue}} props */
function KnownFacts({ issue }) {
  return (
    <div className="semantic-report-facts">
      <strong>关键依据</strong>
      <ul>
        {(issue.known ?? []).map((fact) => (
          <li key={fact}>{fact}</li>
        ))}
      </ul>
    </div>
  );
}

/** @param {{issue: SemanticInsightIssue}} props */
function ValidationNotes({ issue }) {
  return (
    <div className="semantic-report-validation">
      <strong>建议下一步验证</strong>
      <p>{issue.recommendation?.validation_question}</p>
      {(issue.unknown ?? []).length ? (
        <details>
          <summary>还有哪些信息尚未确认</summary>
          <ul>
            {(issue.unknown ?? []).map((question) => (
              <li key={question}>{question}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

/** @param {{index: number, issue: SemanticInsightIssue, catalog: InsightEvidenceCatalog, analysisContext: string}} props */
export function SemanticInsightArticle({ index, issue, catalog, analysisContext }) {
  const terms = analysisContextTerms(analysisContext);
  const readiness = issue.readiness ?? { status: "diagnostic_only" };
  const headingId = `semantic-insight-${issue.id}`;
  return (
    <section
      className={`semantic-report-insight ${issue.kind}`}
      aria-labelledby={headingId}
    >
      <header>
        <span className="semantic-report-number">{index}.</span>
        <div>
          <p>
            {insightKindLabels[issue.kind]} · {readiness.label}
          </p>
          <h3 id={headingId}>{issue.title}</h3>
        </div>
      </header>

      <p className="semantic-report-lead">{issue.evidence_explanation}</p>
      <p className="semantic-report-metrics">
        {issueMetricSummary(issue.metrics ?? {})}
      </p>
      <KnownFacts issue={issue} />
      <IssueLocation issue={issue} catalog={catalog} />
      <ValidationNotes issue={issue} />

      <div className="semantic-report-evidence">
        <DecisionEvidenceDetails
          selectedIssue={issue}
          catalog={catalog}
          terms={terms}
        />
      </div>
    </section>
  );
}
