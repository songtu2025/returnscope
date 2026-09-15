import { CaretRight } from "@phosphor-icons/react";

import { classNames } from "../../lib/presentation";
import { displayProductText, productMatchKey } from "./productMatchPolicy";

/**
 * @param {{
 *   group: import("./productMatchPolicy").ProductMatchGroup,
 *   workbench: ReturnType<typeof import("./useProductMatchWorkbench").useProductMatchWorkbench>
 * }} props
 */
function ProductMatchGroupEditor({ group, workbench }) {
  const {
    categoryAs,
    categoryBsByA,
    drafts,
    selectDraftCategoryA,
    selectedProductKeys,
    showAllGroupKeys,
    toggleGroupProducts,
    toggleProductSelected,
    toggleShowAll,
    updateDraft,
  } = workbench;
  const showAll = showAllGroupKeys.has(group.key);

  return (
    <div className="product-match-examples">
      <div className="product-match-examples-heading">
        <div>
          <b>补充商品信息</b>
          <span>可修改 Listing，并从系统品类规则中选择品类。</span>
        </div>
        <label className="product-match-select-group-products">
          <input
            type="checkbox"
            checked={group.items.every((item) =>
              selectedProductKeys.has(productMatchKey(item)),
            )}
            onChange={() => toggleGroupProducts(group)}
          />
          选择本组全部 {group.items.length} 个商品
        </label>
      </div>
      <div className="product-match-editor-list">
        {(showAll ? group.items : group.items.slice(0, 3)).map((item) => {
          const itemKey = productMatchKey(item);
          const draft = drafts[itemKey];
          return (
            <div className="product-match-editor-row" key={item.product_key}>
              <input
                type="checkbox"
                checked={selectedProductKeys.has(itemKey)}
                onChange={() => toggleProductSelected(itemKey)}
                aria-label={`选择商品 ${item.store} ${item.msku}`}
              />
              <div className="product-match-editor-product">
                <span>{item.store}</span>
                <code>{displayProductText(item.msku)}</code>
                <small>
                  {item.match_candidate
                    ? `候选：${displayProductText(item.match_candidate.msku)} · ${item.match_candidate.match_score}%`
                    : "未找到候选，请人工补充"}
                </small>
              </div>
              <label>
                Listing
                <input
                  aria-label={`${item.store} ${item.msku} Listing`}
                  value={draft.listing}
                  onChange={(event) =>
                    updateDraft(item, { listing: event.target.value })
                  }
                />
              </label>
              <label>
                品类A
                <select
                  aria-label={`${item.store} ${item.msku} 品类A`}
                  value={draft.category_a}
                  onChange={(event) => selectDraftCategoryA(item, event.target.value)}
                >
                  <option value="">请选择</option>
                  {categoryAs.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                品类B
                <select
                  aria-label={`${item.store} ${item.msku} 品类B`}
                  value={draft.category_b}
                  onChange={(event) =>
                    updateDraft(item, { category_b: event.target.value })
                  }
                  disabled={!draft.category_a}
                >
                  <option value="">请选择</option>
                  {(categoryBsByA[draft.category_a] ?? []).map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          );
        })}
      </div>
      <button
        type="button"
        className="product-match-show-all"
        onClick={() => toggleShowAll(group.key)}
      >
        {showAll ? "收起" : "查看全部"} {group.items.length} 个销售 SKU
        <CaretRight size={14} />
      </button>
    </div>
  );
}

/**
 * @param {{workbench: ReturnType<typeof import("./useProductMatchWorkbench").useProductMatchWorkbench>}} props
 */
export function ProductMatchGroupList({ workbench }) {
  const {
    confirmGroup,
    confirmedGroupKeys,
    expandedGroupKey,
    selectedGroupKeys,
    toggleExpandedGroup,
    toggleSelectedGroup,
    visibleGroups,
  } = workbench;

  return (
    <div className="product-match-table">
      <div className="product-match-table-head">
        <span />
        <span>站点 / Listing</span>
        <span>异常 SKU</span>
        <span>影响评论</span>
        <span>系统建议</span>
        <span>处理状态</span>
        <span>操作</span>
      </div>
      {visibleGroups.map((group) => {
        const isExpanded = expandedGroupKey === group.key;
        const isConfirmed = confirmedGroupKeys.has(group.key);
        return (
          <article
            className={classNames("product-match-group", isConfirmed && "confirmed")}
            key={group.key}
          >
            <div className="product-match-row">
              <input
                type="checkbox"
                checked={selectedGroupKeys.has(group.key)}
                onChange={() => toggleSelectedGroup(group.key)}
                aria-label={`选择 ${group.store} ${group.listing} 组`}
              />
              <button
                type="button"
                className="product-match-listing"
                onClick={() => toggleExpandedGroup(group.key)}
                aria-expanded={isExpanded}
              >
                <CaretRight size={15} />
                <span>
                  <b>{group.listing}</b>
                  <small>
                    {group.store} · {group.items.length} 个销售 SKU
                  </small>
                </span>
              </button>
              <strong>{group.items.length.toLocaleString()}</strong>
              <strong>{group.commentCount.toLocaleString()}</strong>
              <div className="product-match-suggestion">
                <span className={group.needsReview ? "review" : "high"}>
                  {group.needsReview ? `${group.needsReview} 个需确认` : "规则完全匹配"}
                </span>
                <b>{group.categoryLabel}</b>
                <small>
                  已匹配 {group.matchedCount}/{group.items.length} 个候选商品
                </small>
              </div>
              <span
                className={classNames("product-match-status", isConfirmed && "done")}
              >
                {isConfirmed ? "已确认" : "待处理"}
              </span>
              <button
                type="button"
                className={isConfirmed ? "secondary-button" : "primary-button"}
                disabled={!group.ready || isConfirmed}
                onClick={() => confirmGroup(group.key)}
              >
                {isConfirmed ? "已关联" : "确认关联"}
              </button>
            </div>
            {isExpanded ? (
              <ProductMatchGroupEditor group={group} workbench={workbench} />
            ) : null}
          </article>
        );
      })}
    </div>
  );
}
