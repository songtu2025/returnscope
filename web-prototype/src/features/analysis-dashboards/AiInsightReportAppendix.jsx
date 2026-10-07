import { formatTime } from "../../lib/presentation";
import { reportLabel, STATUS_LABELS } from "./AiInsightReportPresentation";
/** @typedef {import("./analysisDashboardContracts").InsightReport} InsightReport */

/** @param {{attempts: InsightReport[], onSelect: (reportId: string) => void}} props */
function ReportAttemptHistory({ attempts, onSelect }) {
  return (
    <details className="ai-report-attempt-history">
      <summary>
        <span>生成记录</span>
        <small>{attempts.length} 条过程记录</small>
      </summary>
      <div className="ai-report-attempt-list">
        {attempts.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-label={`查看${reportLabel(item)}`}
            onClick={() => onSelect(item.id)}
          >
            <span>
              <b>{reportLabel(item)}</b>
              <small>
                {item.model_name || item.model_key} · {item.reasoning_effort} 推理强度
              </small>
            </span>
            <strong className={item.status}>{STATUS_LABELS[item.status]}</strong>
          </button>
        ))}
      </div>
    </details>
  );
}

/** @param {{attempts: InsightReport[], report: InsightReport, inputTokens: number, outputTokens: number, onSelect: (reportId: string) => void}} props */
export function ReportAppendix({
  attempts,
  report,
  inputTokens,
  outputTokens,
  onSelect,
}) {
  return (
    <>
      {attempts.length > 0 && (
        <ReportAttemptHistory attempts={attempts} onSelect={onSelect} />
      )}

      <footer className="ai-report-footer">
        <span>生成于 {formatTime(report.completed_at)}</span>
        <span>提示词 {report.prompt_version}</span>
        {(inputTokens > 0 || outputTokens > 0) && (
          <span>
            输入 {inputTokens.toLocaleString()} · 输出 {outputTokens.toLocaleString()}{" "}
            tokens
          </span>
        )}
        <small>
          本报告绑定证据哈希 {String(report.evidence_hash || "").slice(0, 12)}
        </small>
      </footer>
    </>
  );
}
