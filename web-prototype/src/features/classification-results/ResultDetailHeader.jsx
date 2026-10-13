import Button from "antd/es/button";
import { ChartBar, DownloadSimple } from "@phosphor-icons/react";
import { api } from "../../api";
import { DeliveryLifecycleControls } from "../../components/DeliveryLifecycleControls";
import { formatTime } from "../../lib/presentation";
import { PUBLISH_LABELS } from "./classificationResultConstants";

/** @param {import("./classificationResultDetailContracts").ResultDetailContext} context */
export function ResultDetailHeader(context) {
  const { result } = context;
  return (
    <header className="result-detail-header">
      <div>
        <span className="result-publish-note">
          {result.deleted_at
            ? "已删除"
            : `版本发布：${PUBLISH_LABELS[result.publish_status] ?? result.publish_status ?? "未提供"}`}
        </span>
        <h1>{result.listing || "未提供 Listing"} 分类结果</h1>
        <p>
          {result.store_site || "未提供店铺/站点"} · 结果 v{result.version} ·{" "}
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
  const { result, route, policy, runPrimaryAction } = context;
  return (
    <div className="result-detail-actions">
      <DeliveryLifecycleControls
        kind="result"
        id={result.version_id}
        name={result.listing || "分类结果"}
        revision={result.revision || 1}
        deleted={Boolean(result.deleted_at)}
        onChanged={context.retry}
      />
      <Button
        type="primary"
        disabled={policy.primary.disabled}
        title={
          policy.primary.disabled ? policy.blockingReason : "使用最新分类结果创建看板"
        }
        icon={<ChartBar size={18} />}
        onClick={runPrimaryAction}
      >
        {policy.primary.label}
      </Button>
      <a
        className="secondary-button"
        href={api.classificationResultDownloadUrl(result.version_id)}
      >
        <DownloadSimple size={18} />
        {route.tab === "history" ? "下载所选历史结果" : "下载当前版本"}
      </a>
    </div>
  );
}
