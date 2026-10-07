import { ShieldCheck, TrendUp, WarningCircle } from "@phosphor-icons/react";
import { formatPercent } from "./returnReasonInsightPresentation";
/** @typedef {ReturnType<typeof import("./analysisContextPresentation").analysisContextTerms>} AnalysisContextTerms */
/** @typedef {import("./analysisDashboardContracts").DashboardInsights} DashboardInsights */
/** @typedef {{data: DashboardInsights, feedbackGroups: boolean, terms: AnalysisContextTerms, loading: boolean, error?: string, onRetry: () => void | Promise<void>}} SummaryTrustMessageProps */
/** @typedef {SummaryTrustMessageProps & {includedCount: number, pendingCount: number, countUnit: string}} SummaryTrustProps */

/** @param {SummaryTrustMessageProps} props */
function TrustMessage({ data, feedbackGroups, terms, loading, error, onRetry }) {
  return (
    <p
      className={loading || error ? "return-insight-refresh-message" : undefined}
      role={loading ? "status" : error ? "alert" : undefined}
    >
      {loading ? (
        "正在更新筛选结果，当前显示上一次结果…"
      ) : error ? (
        <>
          更新失败，当前显示上一次结果。
          <button type="button" className="text-button" onClick={onRetry}>
            重试
          </button>
        </>
      ) : (
        <>
          同一{feedbackGroups ? "反馈组" : terms.recordUnit}
          可命中多个原因，占比之和可能超过 100%。
          {data.group_alignment === "unified-v1" && " 跨版本已统一一级分组。"}
        </>
      )}
    </p>
  );
}

/** @param {SummaryTrustProps} props */
export function ReturnReasonSummaryTrust(props) {
  const { data, terms, includedCount, pendingCount, countUnit } = props;
  return (
    <section className="return-insight-trust" aria-label="数据可信度">
      <div>
        <ShieldCheck size={19} weight="duotone" />
        <span>{terms.includedLabel}</span>
        <b>
          {includedCount.toLocaleString()} {countUnit}
        </b>
      </div>
      <div>
        <TrendUp size={18} />
        <span>问题标签覆盖</span>
        <b>{formatPercent(data.summary?.label_coverage ?? data.label_coverage)}</b>
      </div>
      <div className={pendingCount ? "warning" : ""}>
        <WarningCircle size={18} />
        <span>待复核</span>
        <b>
          {pendingCount.toLocaleString()} {countUnit}
        </b>
      </div>
      <TrustMessage {...props} />
    </section>
  );
}
