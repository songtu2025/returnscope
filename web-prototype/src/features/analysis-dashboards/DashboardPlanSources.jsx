import { CheckCircle } from "@phosphor-icons/react";
import { formatTime } from "../../lib/presentation";
import {
  productCatalogVersionLabel,
  resultSourceVersionNumber,
} from "./dashboardFields";
import { itemVersionId } from "./dashboardCreatePolicy";
import { DashboardQualityScope } from "./DashboardQualityScope";

/** @param {import("./dashboardCreateContracts").DashboardCreateContext & {showQualityScope?: boolean}} context */
export function DashboardPlanSources(context) {
  const {
    blockers,
    warnings,
    currentSources,
    qualityStatuses,
    setQualityStatuses,
    submitting,
    showQualityScope = true,
  } = context;
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
      {warnings.length > 0 && (
        <div className="dashboard-warnings" role="status">
          <b>请核对统计范围</b>
          {warnings.map((warning, index) => (
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
    </div>
  );
}
