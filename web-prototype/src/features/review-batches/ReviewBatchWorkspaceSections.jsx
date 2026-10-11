import {
  ArrowLeft,
  CaretRight,
  CheckCircle,
  MagnifyingGlass,
} from "@phosphor-icons/react";
import Button from "antd/es/button";
import Input from "antd/es/input";
import Select from "antd/es/select";

import { formatTime } from "../../lib/presentation";
import { BATCH_STATUS_LABELS } from "./reviewBatchPresentation";

/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewAction} ReviewAction */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewBatch} ReviewBatch */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewRecordFilters} ReviewRecordFilters */
/** @typedef {"listing" | "productName" | "productSku" | "orderId"} ReviewBusinessFilter */
/** @typedef {readonly [string, string, string, ReviewBusinessFilter]} ReviewFilterField */

/** @type {readonly ReviewFilterField[]} */
const REVIEW_FILTER_FIELDS = [
  ["Listing", "筛选 Listing", "Listing", "listing"],
  ["产品名称", "筛选产品名称", "产品名称", "productName"],
  ["产品 SKU", "筛选产品SKU", "产品SKU", "productSku"],
  ["order-id", "筛选 order-id", "order-id", "orderId"],
];

/** @typedef {{batch: ReviewBatch, pending: number, onBack: () => void, onOpenSource: () => void, onOpenDerived: () => void}} ReviewSummaryProps */

/** @param {ReviewSummaryProps} props */
export function ReviewBatchSummary(props) {
  const { batch, pending, onBack } = props;
  return (
    <>
      <Button
        className="review-batch-back"
        type="text"
        icon={<ArrowLeft size={17} />}
        onClick={onBack}
      >
        返回历史复核记录
      </Button>

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
        <ReviewBatchActions {...props} />
      </header>
      <ReviewBatchProgress batch={batch} pending={pending} />
      <div className="review-batch-readonly" role="status">
        <CheckCircle size={18} />
        历史批次仅供查看；人工修正请进入最新分类结果。
      </div>
    </>
  );
}

/** @param {ReviewSummaryProps} props */
function ReviewBatchActions({ batch, onOpenSource, onOpenDerived }) {
  return (
    <div className="review-batch-header-actions">
      <Button onClick={onOpenSource}>查看来源版本</Button>
      {batch.derived_result_version_id && (
        <Button
          type="primary"
          icon={<CaretRight size={16} />}
          iconPlacement="end"
          onClick={onOpenDerived}
        >
          查看衍生版本
        </Button>
      )}
    </div>
  );
}

/** @param {{batch: ReviewBatch, pending: number}} props */
function ReviewBatchProgress({ batch, pending }) {
  return (
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
  );
}

/** @param {{filters: ReviewRecordFilters, onFilters: (filters: ReviewRecordFilters) => void, onApply: () => void}} props */
export function ReviewRecordFilters({ filters, onFilters, onApply }) {
  return (
    <section className="review-record-filters" aria-label="复核记录筛选">
      <label className="review-filter-field">
        <span>关键词</span>
        <Input
          aria-label="搜索复核记录"
          prefix={<MagnifyingGlass size={17} />}
          placeholder="搜索评论、分类或业务字段"
          value={filters.q}
          onChange={(event) => onFilters({ ...filters, q: event.target.value })}
        />
      </label>
      <label className="review-filter-field">
        <span>处理状态</span>
        <Select
          aria-label="处理状态"
          value={filters.status}
          onChange={(status) => onFilters({ ...filters, status })}
          options={[
            { value: "", label: "全部记录" },
            { value: "pending", label: "待处理" },
            { value: "resolved", label: "已处理" },
            { value: "excluded", label: "已排除" },
          ]}
        />
      </label>
      {REVIEW_FILTER_FIELDS.map(([title, ariaLabel, placeholder, field]) => (
        <label className="review-filter-field" key={field}>
          <span>{title}</span>
          <Input
            aria-label={ariaLabel}
            placeholder={placeholder}
            value={filters[field]}
            onChange={(event) => onFilters({ ...filters, [field]: event.target.value })}
          />
        </label>
      ))}
      <Button type="primary" onClick={onApply}>
        筛选
      </Button>
    </section>
  );
}
