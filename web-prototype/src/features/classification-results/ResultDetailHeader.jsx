import Button from "antd/es/button";
import { ChartBar, DownloadSimple, ListChecks } from "@phosphor-icons/react";
import { api } from "../../api";
import { formatTime } from "../../lib/presentation";
import { PUBLISH_LABELS } from "./classificationResultConstants";

/** @param {import("./classificationResultDetailContracts").ResultDetailContext} context */
export function ResultDetailHeader(context) {
  const { result, policy } = context;
  return (
    <header className="result-detail-header">
      <div>
        <span className={`result-quality-badge ${policy.state}`}>{policy.label}</span>
        <span className="result-publish-note">
          版本发布：
          {PUBLISH_LABELS[result.publish_status] ?? result.publish_status ?? "未提供"}
        </span>
        <h1>{result.listing || "未提供 Listing"} 分类结果</h1>
        <p>
          {result.store_site || "未提供店铺/站点"} · 结果 v{result.version} · 产品信息 v
          {result.product_version} ·{" "}
          {result.standard_name || result.agent_family || "历史分类逻辑"}
          {result.standard_version ? ` V${result.standard_version}` : ""} ·{" "}
          {formatTime(result.published_at)}
        </p>
      </div>
      <ResultDetailActions {...context} />
    </header>
  );
}

/** @param {import("./classificationResultDetailContracts").ResultDetailContext} context */
function ResultDetailActions(context) {
  const { result, createDashboardFromResult, policy, runPrimaryAction } = context;
  return (
    <div className="result-detail-actions">
      <Button
        type="primary"
        disabled={policy.primary.disabled}
        title={policy.primary.disabled ? policy.blockingReason : ""}
        icon={
          policy.primary.kind === "create-dashboard" ? (
            <ChartBar size={18} />
          ) : (
            <ListChecks size={18} />
          )
        }
        onClick={runPrimaryAction}
      >
        {policy.primary.label}
      </Button>
      {policy.secondary?.kind === "create-dashboard" && (
        <Button
          disabled={policy.secondary.disabled}
          title={policy.secondary.disabled ? policy.blockingReason : ""}
          icon={<ChartBar size={18} />}
          onClick={createDashboardFromResult}
        >
          {policy.secondary.label}
        </Button>
      )}
      <a
        className="secondary-button"
        href={api.classificationResultDownloadUrl(result.version_id)}
      >
        <DownloadSimple size={18} /> 下载当前版本
      </a>
    </div>
  );
}
