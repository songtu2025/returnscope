import { CaretRight, Check } from "@phosphor-icons/react";

import { ProductMatchBulkToolbar } from "./ProductMatchBulkToolbar";
import { ProductMatchGroupList } from "./ProductMatchGroupList";
import { useProductMatchWorkbench } from "./useProductMatchWorkbench";

/**
 * @param {{
 *   plan: import("./productMatchPolicy").ProductMatchPlan,
 *   saving: boolean,
 *   onBack: () => void,
 *   onSave: (items: import("./productMatchPolicy").ProductMatchDraft[]) => void
 * }} props
 */
export function ProductMatchWorkbench({ plan, saving, onBack, onSave }) {
  const workbench = useProductMatchWorkbench(plan);
  const {
    allConfirmed,
    confirmedComments,
    confirmedGroupKeys,
    confirmSelectedGroups,
    filter,
    groups,
    highConfidenceGroupCount,
    reviewGroupCount,
    saveItems,
    selectFilter,
    selectedComments,
    selectedGroupKeys,
    toggleAllGroups,
  } = workbench;
  const blockedCommentCount =
    plan.unresolved_product_comment_count ?? plan.blocked_count ?? 0;
  const filters = [
    { value: "all", label: "全部", count: groups.length },
    {
      value: "high",
      label: "高匹配建议",
      count: highConfidenceGroupCount,
    },
    { value: "review", label: "需人工确认", count: reviewGroupCount },
  ];

  return (
    <div className="standard-page product-match-page">
      <nav className="product-match-breadcrumb" aria-label="创建任务步骤">
        <button type="button" onClick={onBack}>
          创建分析任务
        </button>
        <CaretRight size={13} />
        <button type="button" onClick={onBack}>
          确认执行计划
        </button>
        <CaretRight size={13} />
        <span>处理商品匹配异常</span>
      </nav>
      <header className="product-match-heading">
        <div>
          <h1>处理商品匹配异常</h1>
          <p>
            系统已用结构化 SKU 规则匹配现有商品。确认关联后，销售 SKU 将继承商品的
            Listing 与品类信息。
          </p>
        </div>
        <div className="product-match-progress" aria-live="polite">
          已处理{" "}
          <b>
            {confirmedGroupKeys.size}/{groups.length}
          </b>{" "}
          组 · 覆盖{" "}
          <b>
            {confirmedComments.toLocaleString()}/{blockedCommentCount.toLocaleString()}
          </b>{" "}
          条评论
        </div>
      </header>

      <div className="product-match-layout">
        <ol className="product-match-steps" aria-label="任务准备进度">
          <li className="done">
            <span>
              <Check size={14} />
            </span>
            <div>
              <b>任务配置</b>
              <small>已完成</small>
            </div>
          </li>
          <li className="active">
            <span>2</span>
            <div>
              <b>商品匹配</b>
              <small>处理中</small>
            </div>
          </li>
          <li>
            <span>3</span>
            <div>
              <b>品类检查</b>
              <small>待处理</small>
            </div>
          </li>
          <li>
            <span>4</span>
            <div>
              <b>确认执行</b>
              <small>待处理</small>
            </div>
          </li>
        </ol>

        <section className="product-match-workspace">
          <div className="product-match-filters" role="tablist" aria-label="匹配筛选">
            {filters.map(({ value, label, count }) => (
              <button
                key={value}
                type="button"
                className={filter === value ? "active" : ""}
                onClick={() => selectFilter(value)}
                role="tab"
                aria-selected={filter === value}
              >
                {label}（{count}）
              </button>
            ))}
          </div>

          <ProductMatchBulkToolbar workbench={workbench} />
          <ProductMatchGroupList workbench={workbench} />
        </section>
      </div>

      <footer className="product-match-footer">
        <div>
          <input
            type="checkbox"
            checked={groups.length > 0 && selectedGroupKeys.size === groups.length}
            onChange={toggleAllGroups}
            aria-label="选择全部 Listing 组"
          />
          <span>
            已选择 <b>{selectedGroupKeys.size}</b> 组 · 覆盖{" "}
            <b>{selectedComments.toLocaleString()}</b> 条评论
          </span>
        </div>
        <div>
          <button type="button" className="secondary-button" onClick={onBack}>
            返回执行计划
          </button>
          <button
            type="button"
            className="secondary-button match-confirm-selected"
            disabled={selectedGroupKeys.size === 0}
            onClick={confirmSelectedGroups}
          >
            确认所选关联
          </button>
          <button
            type="button"
            className="primary-button"
            disabled={!allConfirmed || saving}
            onClick={() => onSave(saveItems)}
          >
            {saving ? "正在保存…" : "保存关联并重新生成计划"}
          </button>
        </div>
      </footer>
    </div>
  );
}
