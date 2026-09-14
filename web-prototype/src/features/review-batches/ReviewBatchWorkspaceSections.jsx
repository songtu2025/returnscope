import {
  ArrowLeft,
  CaretRight,
  ChartBar,
  CheckCircle,
  EyeSlash,
  MagnifyingGlass,
  PencilSimple,
} from "@phosphor-icons/react";

import { formatTime } from "../../lib/presentation";
import { BATCH_STATUS_LABELS } from "./reviewBatchPresentation";

export function ReviewBatchSummary({
  batch,
  pending,
  readOnly,
  onBack,
  onOpenSource,
  onOpenDerived,
  onCreateDashboard,
  onOpenPublish,
}) {
  return (
    <>
      <button className="text-button review-batch-back" onClick={onBack}>
        <ArrowLeft size={17} /> 返回复核批次列表
      </button>

      <header className="review-batch-workspace-header">
        <div>
          <span className={`review-batch-status ${batch.status}`}>
            {BATCH_STATUS_LABELS[batch.status] ?? batch.status}
          </span>
          <h1>{batch.listing || "分类结果"} 复核批次</h1>
          <p>
            来源分类结果 v{batch.base_version_no ?? "—"} · 创建人{" "}
            {batch.creator_name || "未提供"} · 批次修订 #{batch.revision}
          </p>
        </div>
        <div className="review-batch-header-actions">
          <button className="secondary-button" onClick={onOpenSource}>
            查看来源版本
          </button>
          {readOnly ? (
            <>
              <button className="primary-button" onClick={onOpenDerived}>
                查看衍生版本 <CaretRight size={16} />
              </button>
              <button className="secondary-button" onClick={onCreateDashboard}>
                <ChartBar size={17} /> 创建分析看板
              </button>
            </>
          ) : (
            <button
              className="primary-button"
              disabled={pending > 0 || Number(batch.record_count || 0) === 0}
              title={
                Number(batch.record_count || 0) === 0
                  ? "该历史批次没有可处理记录，不能发布"
                  : pending > 0
                    ? `还剩 ${pending} 条需处理，全部处理后才能发布`
                    : ""
              }
              onClick={onOpenPublish}
            >
              {Number(batch.record_count || 0) === 0
                ? "无可处理记录"
                : pending > 0
                  ? `还剩 ${pending} 条需处理`
                  : "发布派生版本"}
            </button>
          )}
        </div>
      </header>

      <section className="review-batch-progress" aria-label="复核批次进度">
        <div>
          <span>批次记录</span>
          <b>{Number(batch.record_count || 0).toLocaleString()}</b>
        </div>
        <div>
          <span>已确认 / 修改</span>
          <b>{Number(batch.resolved_count || 0).toLocaleString()}</b>
        </div>
        <div>
          <span>已排除</span>
          <b>{Number(batch.excluded_count || 0).toLocaleString()}</b>
        </div>
        <div className={pending ? "has-pending" : "is-complete"}>
          <span>待处理</span>
          <b>{pending.toLocaleString()}</b>
        </div>
        <div>
          <span>最后更新</span>
          <b>{formatTime(batch.updated_at)}</b>
        </div>
      </section>

      {readOnly && (
        <div className="review-batch-readonly" role="status">
          <CheckCircle size={18} />
          此批次已发布为分类结果 v{batch.derived_version_no ?? "—"}，当前内容只读。
        </div>
      )}
    </>
  );
}

export function ReviewRecordFilters({ filters, onFilters, onApply }) {
  return (
    <section className="review-record-filters" aria-label="复核记录筛选">
      <label className="review-filter-field">
        <span>关键词</span>
        <div className="review-record-search">
          <MagnifyingGlass size={17} />
          <input
            aria-label="搜索复核记录"
            placeholder="搜索评论、分类或业务字段"
            value={filters.q}
            onChange={(event) => onFilters({ ...filters, q: event.target.value })}
          />
        </div>
      </label>
      <label className="review-filter-field">
        <span>处理状态</span>
        <select
          aria-label="处理状态"
          value={filters.status}
          onChange={(event) => onFilters({ ...filters, status: event.target.value })}
        >
          <option value="">全部记录</option>
          <option value="pending">待处理</option>
          <option value="resolved">已处理</option>
          <option value="excluded">已排除</option>
        </select>
      </label>
      {[
        ["Listing", "筛选 Listing", "Listing", "listing"],
        ["产品名称", "筛选产品名称", "产品名称", "productName"],
        ["产品 SKU", "筛选产品SKU", "产品SKU", "productSku"],
        ["order-id", "筛选 order-id", "order-id", "orderId"],
      ].map(([title, ariaLabel, placeholder, field]) => (
        <label className="review-filter-field" key={field}>
          <span>{title}</span>
          <input
            aria-label={ariaLabel}
            placeholder={placeholder}
            value={filters[field]}
            onChange={(event) => onFilters({ ...filters, [field]: event.target.value })}
          />
        </label>
      ))}
      <button className="primary-button" onClick={onApply}>
        筛选
      </button>
    </section>
  );
}

export function ReviewBulkToolbar({ checkedCount, onBulk, onClear }) {
  if (!checkedCount) return null;

  return (
    <section className="review-bulk-toolbar" aria-label="批量复核操作">
      <b>已选择 {checkedCount} 条待处理记录</b>
      <div>
        <button className="secondary-button" onClick={() => onBulk("confirm")}>
          <CheckCircle size={17} /> 批量确认
        </button>
        <button className="secondary-button" onClick={() => onBulk("modify")}>
          <PencilSimple size={17} /> 批量修改分类
        </button>
        <button className="secondary-button" onClick={() => onBulk("exclude")}>
          <EyeSlash size={17} /> 批量排除
        </button>
        <button className="text-button" onClick={onClear}>
          取消选择
        </button>
      </div>
    </section>
  );
}
