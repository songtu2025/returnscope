import { SectionHeading } from "./AiInsightReportCommon";
export { ReportInformationSection } from "./AiInsightReportInformation";
export { ReportBoundarySection } from "./AiInsightReportBoundary";
export { ReportAppendix } from "./AiInsightReportAppendix";
/** @typedef {import("./analysisDashboardContracts").ReportAction} ReportAction */
/** @typedef {import("./analysisDashboardContracts").ReportFinding} ReportFinding */
/** @typedef {import("./analysisDashboardContracts").ReportDiagnostic} ReportDiagnostic */
/** @typedef {import("./analysisDashboardContracts").ReportReason} ReportReason */

/** @param {{primaryAction: ReportAction}} props */
function PrimaryAction({ primaryAction }) {
  return (
    <article className="ai-report-primary-action">
      <span>{primaryAction.priority} · 首要行动</span>
      <h4>{primaryAction.target || "对应问题范围"}</h4>
      <p>{primaryAction.action}</p>
      <div>
        <b>验证标准</b>
        <p>{primaryAction.success_signal}</p>
      </div>
      {primaryAction.rationale && (
        <details>
          <summary>查看优先依据</summary>
          <p>{primaryAction.rationale}</p>
        </details>
      )}
    </article>
  );
}

/** @param {{followupActions: ReportAction[]}} props */
function FollowupActions({ followupActions }) {
  return (
    <div className="ai-report-followup-actions">
      {followupActions.map((action) => (
        <article key={action.id || action.action}>
          <span>{action.priority}</span>
          <div>
            <h4>{action.target || "对应问题范围"}</h4>
            <p>{action.action}</p>
            <small>
              <b>验证：</b>
              {action.success_signal}
            </small>
            {action.rationale && (
              <details>
                <summary>查看行动依据</summary>
                <p>{action.rationale}</p>
              </details>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}

/** @param {{primaryAction?: ReportAction, followupActions: ReportAction[], informationFinding?: ReportFinding, informationDiagnostic?: ReportDiagnostic, informationReason?: ReportReason}} props */
export function ReportActionsSection({
  primaryAction,
  followupActions,
  informationFinding,
  informationDiagnostic,
  informationReason,
}) {
  return (
    <section className="ai-report-section" id="report-actions">
      <SectionHeading
        number={
          informationFinding || informationDiagnostic || informationReason ? "04" : "03"
        }
        title="按证据强度执行行动计划"
        description="每项行动绑定目标对象和可观察的验证条件。"
      />
      {primaryAction && <PrimaryAction primaryAction={primaryAction} />}
      {followupActions.length > 0 && (
        <FollowupActions followupActions={followupActions} />
      )}
    </section>
  );
}
