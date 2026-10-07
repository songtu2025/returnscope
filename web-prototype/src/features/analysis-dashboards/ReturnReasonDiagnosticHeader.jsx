import { Info } from "@phosphor-icons/react";
import { formatPercent } from "./returnReasonInsightPresentation";
/** @typedef {import("./analysisDashboardContracts").InsightReason} InsightReason */
/** @typedef {ReturnType<typeof import("./analysisContextPresentation").analysisContextTerms>} AnalysisContextTerms */

/** @param {{label: string, value: string}} props */
function InsightStat({ label, value }) {
  return (
    <div className="return-insight-stat">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

/** @param {{detailLoading: boolean, detailError: string, subjectLabel: string, onDetailRetry?: () => void | Promise<void>}} props */
function DiagnosticDetailStatus({
  detailLoading,
  detailError,
  subjectLabel,
  onDetailRetry,
}) {
  return (
    <p role={detailLoading ? "status" : detailError ? "alert" : undefined}>
      {detailError ? (
        <>
          原因详情更新失败 · 显示上次结果
          {onDetailRetry && (
            <button type="button" className="text-button" onClick={onDetailRetry}>
              重试
            </button>
          )}
        </>
      ) : detailLoading ? (
        "原因详情更新中 · 显示上次结果"
      ) : subjectLabel ? (
        `原因诊断 · ${subjectLabel}`
      ) : (
        "原因诊断"
      )}
    </p>
  );
}

/** @param {{selected: InsightReason, terms: AnalysisContextTerms}} props */
function DiagnosticStats({ selected, terms }) {
  return (
    <div className="return-diagnostic-metrics">
      <InsightStat label="相关评论" value={`${selected.record_count} 条`} />
      <InsightStat
        label={terms.shareLabel}
        value={formatPercent(selected.percentage)}
      />
      <InsightStat label="核心原因率" value={formatPercent(selected.primary_rate)} />
    </div>
  );
}

/** @param {{selected: InsightReason, showDefinition: boolean}} props */
function DiagnosticDefinition({ selected, showDefinition }) {
  if (!showDefinition) return null;
  return (
    <div className="return-diagnostic-definition">
      <b>{selected.label}</b>
      <span>
        统计包含该问题标签的去重评论；核心原因率表示该标签进入评论的
        primary_label_codes，不等同于唯一责任归因。
      </span>
    </div>
  );
}

/** @param {{selected: InsightReason, subjectLabel?: string, detailLoading?: boolean, detailError?: string, onDetailRetry?: () => void | Promise<void>, terms: AnalysisContextTerms, showDefinition: boolean, onToggleDefinition: () => void}} props */
export function ReturnReasonDiagnosticHeader({
  selected,
  subjectLabel = "",
  detailLoading = false,
  detailError = "",
  onDetailRetry,
  terms,
  showDefinition,
  onToggleDefinition,
}) {
  return (
    <>
      <header className="return-diagnostic-header">
        <div className="return-diagnostic-title">
          <span>2</span>
          <div>
            <DiagnosticDetailStatus
              detailLoading={detailLoading}
              detailError={detailError}
              subjectLabel={subjectLabel}
              onDetailRetry={onDetailRetry}
            />
            <h2>{selected.label}</h2>
          </div>
        </div>
        <DiagnosticStats selected={selected} terms={terms} />
        <button
          className={showDefinition ? "active" : ""}
          aria-expanded={showDefinition}
          onClick={onToggleDefinition}
        >
          <Info size={16} /> 查看定义
        </button>
      </header>
      <DiagnosticDefinition selected={selected} showDefinition={showDefinition} />
    </>
  );
}
