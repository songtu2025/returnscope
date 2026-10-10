import { CheckCircle } from "@phosphor-icons/react";
import { formatTime } from "../../lib/presentation";
import {
  productCatalogVersionLabel,
  resultSourceVersionNumber,
} from "./dashboardFields";
import { itemVersionId } from "./dashboardCreatePolicy";
import { DashboardQualityScope } from "./DashboardQualityScope";

/** @param {import("./dashboardCreateContracts").DashboardCreateContext & {showQualityScope?: boolean, children?: import("react").ReactNode}} context */
export function DashboardPlanSources(context) {
  const {
    blockers,
    warnings,
    currentSources,
    qualityStatuses,
    setQualityStatuses,
    submitting,
    showQualityScope = true,
    state,
    summary,
    resultVersionIds,
    children,
  } = context;
  const scopeWarnings = warnings.filter(
    (warning) =>
      !showQualityScope ||
      !["quality_scope_limited", "quality_review_pending"].includes(warning.type || ""),
  );
  return (
    <div className="dashboard-confirm-main">
      <header>
        <CheckCircle size={24} />
        <div>
          <b>执行计划已生成</b>
          <span>请核对每个 Listing 使用的结果版本，再生成不可变数据集。</span>
        </div>
      </header>
      {showQualityScope && (
        <DashboardPlanStats
          resultVersionIds={resultVersionIds}
          currentSources={currentSources}
          summary={summary}
        />
      )}
      {showQualityScope && (
        <DashboardQualityScope
          statuses={qualityStatuses}
          onChange={setQualityStatuses}
          disabled={submitting}
        />
      )}
      {blockers.length > 0 && (
        <div className="dashboard-blockers" role="alert">
          <b>仍有阻断项</b>
          {blockers.map((blocker, index) => (
            <span key={blocker.type || index}>
              {blocker.message || String(blocker)}
            </span>
          ))}
        </div>
      )}
      {showQualityScope && (
        <div className="dashboard-scope-feedback" aria-busy={state.loading}>
          <p className="dashboard-scope-update" role="status" aria-live="polite">
            {state.loading
              ? "正在更新统计范围…"
              : state.error
                ? "统计范围更新失败"
                : "统计范围已更新"}
          </p>
          <DashboardCoverageNote summary={summary} />
        </div>
      )}
      {scopeWarnings.length > 0 && (
        <div className="dashboard-warnings" role="status">
          <b>请核对统计范围</b>
          {scopeWarnings.map((warning, index) => (
            <span key={warning.type || index}>
              {warning.message || String(warning)}
            </span>
          ))}
        </div>
      )}
      <div className="dashboard-source-mapping">
        <div className="dashboard-source-head">
          <span>店铺/站点</span>
          <span>Listing</span>
          <span>结果版本</span>
          <span>产品信息版本</span>
          <span>记录数</span>
          <span>发布时间</span>
        </div>
        {currentSources.map((source) => (
          <div key={itemVersionId(source)}>
            <span>{source.store_site || "未提供"}</span>
            <b>{source.listing || "未提供"}</b>
            <span>v{resultSourceVersionNumber(source) ?? "-"}</span>
            <span title={productCatalogVersionLabel(source)}>
              {productCatalogVersionLabel(source)}
            </span>
            <span>{Number(source.record_count || 0).toLocaleString()}</span>
            <span>{formatTime(source.published_at)}</span>
          </div>
        ))}
      </div>
      {children}
    </div>
  );
}

/** @param {Pick<Parameters<typeof DashboardPlanSources>[0], "resultVersionIds" | "currentSources" | "summary" >} props */
function DashboardPlanStats({ resultVersionIds, currentSources, summary }) {
  return (
    <div className="dashboard-plan-stats">
      <span>
        结果版本
        <b>{summary.source_count ?? resultVersionIds.length}</b>
      </span>
      <span>
        Listing
        <b>{summary.listing_count ?? currentSources.length}</b>
      </span>
      <span>
        {summary.counting_basis === "feedback_group" ? "反馈组" : "记录"}
        <b>
          {summary.record_count == null
            ? "暂无统计"
            : Number(summary.record_count).toLocaleString()}
        </b>
      </span>
    </div>
  );
}
/** @param {Pick<Parameters<typeof DashboardPlanSources>[0], "summary" >} props */
function DashboardCoverageNote({ summary }) {
  return (
    <div className="dashboard-coverage-note">
      <b>
        纳入 {Number(summary.record_count || 0).toLocaleString()} /{" "}
        {Number(
          summary.total_record_count ?? summary.record_count ?? 0,
        ).toLocaleString()}{" "}
        {summary.counting_basis === "feedback_group" ? "个反馈组" : "条记录"}
      </b>
      <span>
        待处理 {Number(summary.pending_review_record_count || 0).toLocaleString()}{" "}
        {summary.counting_basis === "feedback_group" ? "个反馈组" : "条"}
        （含待复核和不可用）；已忽略{" "}
        {Number(summary.excluded_record_count || 0).toLocaleString()}{" "}
        {summary.counting_basis === "feedback_group" ? "个反馈组" : "条"}。
      </span>
    </div>
  );
}
