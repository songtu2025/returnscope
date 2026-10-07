import { Eye, ShieldCheck } from "@phosphor-icons/react";
/** @typedef {import("./analysisDashboardContracts").DashboardDecisionState} DashboardDecisionState */
/** @typedef {import("./analysisDashboardContracts").ReportReadiness} ReportReadiness */
/** @typedef {import("./analysisDashboardContracts").DecisionReportIssue} DecisionReportIssue */

/** @param {{selectedIssue: DecisionReportIssue, selectedDecision: string, isSaving: boolean, readiness: ReportReadiness, onDecision: (issueId: string, status: string) => void | Promise<void>}} props */
function DecisionChoices({
  selectedIssue,
  selectedDecision,
  isSaving,
  readiness,
  onDecision,
}) {
  return (
    <div className="ai-decision-actions">
      <button
        className={selectedDecision === "ignored" ? "active" : ""}
        disabled={isSaving}
        aria-pressed={selectedDecision === "ignored"}
        onClick={() => onDecision(selectedIssue.id, "ignored")}
      >
        暂不处理
      </button>
      <button
        className={selectedDecision === "watching" ? "active" : ""}
        disabled={isSaving}
        aria-pressed={selectedDecision === "watching"}
        onClick={() => onDecision(selectedIssue.id, "watching")}
      >
        <Eye size={16} /> 继续观察
      </button>
      <button
        className={`primary ${selectedDecision === "verify" ? "active" : ""}`}
        disabled={isSaving || readiness.status === "unusable"}
        aria-pressed={selectedDecision === "verify"}
        onClick={() => onDecision(selectedIssue.id, "verify")}
      >
        <ShieldCheck size={16} /> {isSaving ? "正在保存…" : "建议验证"}
      </button>
      <div>
        <span>报告输出</span>
        <b>验证问题 + 所需证据</b>
      </div>
    </div>
  );
}

/** @param {{selectedIssue: DecisionReportIssue, selectedDecision: string, decisionState: DashboardDecisionState, readiness: ReportReadiness, onDecision: (issueId: string, status: string) => void | Promise<void>}} props */
export function DecisionActions({
  selectedIssue,
  selectedDecision,
  decisionState,
  readiness,
  onDecision,
}) {
  const isSaving = decisionState?.loading && decisionState.issueId === selectedIssue.id;
  return (
    <section className="ai-decision-recommendation">
      <header>
        <div>
          <h4>选择处理方式</h4>
          <p>{selectedIssue.recommendation?.rationale}</p>
        </div>
        <span>{selectedIssue.recommendation?.label}</span>
      </header>
      <ul>
        {(selectedIssue.recommendation?.suggested_evidence ?? []).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      {decisionState?.error && decisionState.issueId === selectedIssue.id && (
        <p className="ai-decision-error" role="alert">
          {decisionState.error}
        </p>
      )}
      <DecisionChoices
        selectedIssue={selectedIssue}
        selectedDecision={selectedDecision}
        isSaving={isSaving}
        readiness={readiness}
        onDecision={onDecision}
      />
    </section>
  );
}
