import { CaretRight, DownloadSimple } from "@phosphor-icons/react";

import { api } from "../../api";
import { formatTime } from "../../lib/presentation";
import { PUBLISH_LABELS } from "./classificationResultConstants";
import { resultActionPolicy } from "./resultActionPolicy";

function productNames(result) {
  const names = Array.isArray(result.product_names)
    ? result.product_names.filter(Boolean)
    : result.product_name
      ? [result.product_name]
      : [];
  return names;
}

export function ResultPoolRow({
  result,
  onOpen,
  onPrimary,
  selectable,
  selected,
  onToggle,
}) {
  const names = productNames(result);
  const policy = resultActionPolicy(result);
  const disabledReason = policy.dashboardSelectable ? "" : policy.blockingReason;
  return (
    <article className={`result-pool-row ${selected ? "is-selected" : ""}`} role="row">
      {selectable && (
        <label className="result-selection-cell" title={disabledReason}>
          <input
            type="checkbox"
            aria-label={`选择 ${result.listing || "未提供 Listing"} 结果 v${result.version}`}
            checked={selected}
            disabled={Boolean(disabledReason)}
            onChange={onToggle}
          />
          {disabledReason && <small>{disabledReason}</small>}
        </label>
      )}
      <div className="result-state-cell">
        <span className={`result-quality-badge ${policy.state}`}>{policy.label}</span>
        <small>
          {policy.state === "needs_review"
            ? "可先建立已可用数据看板，也可继续复核"
            : `版本发布：${PUBLISH_LABELS[result.publish_status] ?? result.publish_status ?? "未提供"}`}
        </small>
      </div>
      <div className="result-listing-cell">
        <button className="text-button result-listing-link" onClick={onOpen}>
          {result.listing || "未提供 Listing"}
        </button>
        <span>{result.store_site || "未提供店铺/站点"}</span>
        <small>结果 v{result.version}</small>
      </div>
      <div className="result-product-cell">
        <b title={names.join("、")}>{names[0] || "未提供"}</b>
        {names.length > 1 && <span>另有 {names.length - 1} 个产品名称</span>}
        <small>产品信息 v{result.product_version}</small>
      </div>
      <div className="result-scale-cell">
        <b>{Number(result.record_count || 0).toLocaleString()} 条记录</b>
        <span>{Number(result.unit_count || 0).toLocaleString()} 个分类单元</span>
      </div>
      <div className="result-time-cell">
        <b>{formatTime(result.published_at || result.created_at)}</b>
        <span>
          {result.standard_name || result.agent_family || "未提供分类标准"}
          {result.standard_version ? ` · V${result.standard_version}` : ""}
        </span>
      </div>
      <div className="result-row-actions">
        <button
          className="secondary-button compact-button"
          disabled={policy.primary.disabled}
          title={policy.primary.disabled ? policy.blockingReason : ""}
          onClick={onPrimary}
        >
          {policy.primary.label}
          <CaretRight size={15} />
        </button>
        <a
          className="secondary-button compact-button"
          href={api.classificationResultDownloadUrl(result.version_id)}
        >
          <DownloadSimple size={15} />
          下载
        </a>
      </div>
    </article>
  );
}

export function InsightSelectionBar({ selected, totals, onCancel, onGenerate }) {
  return (
    <div className="insight-selection-bar" role="status">
      <div>
        <b>已选 {selected.length} 项</b>
        <span>{totals.records.toLocaleString()} 条记录</span>
        <span>{totals.units.toLocaleString()} 个分类单元</span>
      </div>
      <button className="primary-button" onClick={onGenerate}>
        生成 AI 洞察
      </button>
      <button className="secondary-button" onClick={onCancel}>
        取消选择
      </button>
    </div>
  );
}

export function DashboardSelectionBar({ selected, onClear, onContinue }) {
  const listingCount = new Set(
    selected.map((item) => `${item.store_site}::${item.listing}`),
  ).size;
  return (
    <aside className="dashboard-selection-bar" aria-label="看板数据选择">
      <div>
        <b>已选 {selected.length} 个结果版本</b>
        <span>覆盖 {listingCount} 个 Listing</span>
      </div>
      <button className="text-button" disabled={!selected.length} onClick={onClear}>
        清空
      </button>
      <button
        className="primary-button"
        disabled={!selected.length}
        onClick={onContinue}
      >
        检查并生成 <CaretRight size={17} />
      </button>
    </aside>
  );
}
