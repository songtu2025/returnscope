import { useState } from "react";
import { CaretRight, Check } from "@phosphor-icons/react";
import { classNames } from "../../lib/presentation";

function buildProductMatchGroups(items) {
  const byListing = new Map();
  items.forEach((item) => {
    const listing =
      item.suggested_listing || item.match_candidate?.listing || "待补充 Listing";
    const key = `${item.store}\u001f${listing}`;
    if (!byListing.has(key)) {
      byListing.set(key, {
        key,
        store: item.store,
        listing,
        items: [],
        commentCount: 0,
        recordCount: 0,
      });
    }
    const group = byListing.get(key);
    group.items.push(item);
    group.commentCount += Number(item.comment_count || 0);
    group.recordCount += Number(item.record_count || 0);
  });
  return Array.from(byListing.values())
    .map((group) => {
      const matched = group.items.filter((item) => {
        const product = item.resolved_product;
        return Boolean(
          product?.store &&
          product?.listing &&
          product?.category_a &&
          product?.category_b,
        );
      });
      const needsReview = group.items.filter(
        (item) => item.match_status !== "high_confidence",
      ).length;
      const categories = Array.from(
        new Set(
          matched.map(
            (item) =>
              `${item.resolved_product.category_a}\u001f${item.resolved_product.category_b}`,
          ),
        ),
      );
      return {
        ...group,
        matchedCount: matched.length,
        needsReview,
        ready: matched.length === group.items.length,
        categoryLabel:
          categories.length === 1
            ? categories[0].split("\u001f").join(" > ")
            : `${categories.length} 种品类规则`,
      };
    })
    .sort((left, right) => right.commentCount - left.commentCount);
}

function displayProductText(value) {
  return String(value || "").replaceAll("&amp;", "&");
}

function productMatchKey(item) {
  return `${item.store}\u001f${item.msku}`;
}

function initialProductMatch(item) {
  const candidate = item.match_candidate ?? {};
  return {
    store: item.store || candidate.store || "",
    msku: item.msku,
    listing: candidate.listing || item.suggested_listing || "",
    category_a: candidate.category_a || item.current_category_a || "",
    category_b: candidate.category_b || item.current_category_b || "",
    product_name: candidate.product_name || item.product_name || "",
  };
}

export function ProductMatchWorkbench({ plan, saving, onBack, onSave }) {
  const sourceItems = (plan.unresolved_products ?? []).filter(
    (item) => item.editable && item.store,
  );
  const [drafts, setDrafts] = useState(() =>
    Object.fromEntries(
      sourceItems.map((item) => [productMatchKey(item), initialProductMatch(item)]),
    ),
  );
  const matchedItems = sourceItems.map((item) => ({
    ...item,
    resolved_product: drafts[productMatchKey(item)],
  }));
  const groups = buildProductMatchGroups(matchedItems);
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState(() => new Set());
  const [confirmed, setConfirmed] = useState(() => new Set());
  const [expanded, setExpanded] = useState(groups[0]?.key ?? "");
  const [showAll, setShowAll] = useState(() => new Set());
  const categoryAs = Array.from(
    new Set((plan.category_options ?? []).map((item) => item.category_a)),
  ).sort();
  const categoryBs = (categoryA) =>
    (plan.category_options ?? [])
      .filter((item) => item.category_a === categoryA)
      .map((item) => item.category_b);
  const visibleGroups = groups.filter((group) => {
    if (filter === "high") return group.needsReview === 0;
    if (filter === "review") return group.needsReview > 0;
    return true;
  });
  const readyGroups = groups.filter((group) => group.ready);
  const confirmedComments = groups
    .filter((group) => confirmed.has(group.key))
    .reduce((total, group) => total + group.commentCount, 0);
  const selectedGroups = groups.filter((group) => selected.has(group.key));
  const selectedComments = selectedGroups.reduce(
    (total, group) => total + group.commentCount,
    0,
  );
  const allConfirmed =
    readyGroups.length === groups.length && confirmed.size === groups.length;

  const toggleSelected = (groupKey) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(groupKey)) next.delete(groupKey);
      else next.add(groupKey);
      return next;
    });
  };
  const confirmGroup = (groupKey) => {
    setConfirmed((current) => new Set(current).add(groupKey));
  };
  const confirmSelected = () => {
    setConfirmed((current) => {
      const next = new Set(current);
      selectedGroups
        .filter((group) => group.ready)
        .forEach((group) => {
          next.add(group.key);
        });
      return next;
    });
  };
  const updateDraft = (item, changes) => {
    const itemKey = productMatchKey(item);
    setDrafts((current) => ({
      ...current,
      [itemKey]: { ...current[itemKey], ...changes },
    }));
    const groupKey = `${item.store}\u001f${
      item.suggested_listing || item.match_candidate?.listing || "待补充 Listing"
    }`;
    setConfirmed((current) => {
      const next = new Set(current);
      next.delete(groupKey);
      return next;
    });
  };
  const save = () => {
    const items = groups.flatMap((group) =>
      group.items.map((item) => drafts[productMatchKey(item)]),
    );
    onSave(items);
  };

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
            {confirmed.size}/{groups.length}
          </b>{" "}
          组 · 覆盖{" "}
          <b>
            {confirmedComments.toLocaleString()}/
            {(
              plan.unresolved_product_comment_count ?? plan.blocked_count
            ).toLocaleString()}
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
            {[
              ["all", "全部", groups.length],
              [
                "high",
                "高匹配建议",
                groups.filter((group) => group.needsReview === 0).length,
              ],
              [
                "review",
                "需人工确认",
                groups.filter((group) => group.needsReview > 0).length,
              ],
            ].map(([value, label, count]) => (
              <button
                key={value}
                type="button"
                className={filter === value ? "active" : ""}
                onClick={() => setFilter(value)}
                role="tab"
                aria-selected={filter === value}
              >
                {label}（{count}）
              </button>
            ))}
          </div>

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
              const isExpanded = expanded === group.key;
              const isConfirmed = confirmed.has(group.key);
              return (
                <article
                  className={classNames(
                    "product-match-group",
                    isConfirmed && "confirmed",
                  )}
                  key={group.key}
                >
                  <div className="product-match-row">
                    <input
                      type="checkbox"
                      checked={selected.has(group.key)}
                      onChange={() => toggleSelected(group.key)}
                      aria-label={`选择 ${group.store} ${group.listing} 组`}
                    />
                    <button
                      type="button"
                      className="product-match-listing"
                      onClick={() => setExpanded(isExpanded ? "" : group.key)}
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
                        {group.needsReview
                          ? `${group.needsReview} 个需确认`
                          : "规则完全匹配"}
                      </span>
                      <b>{group.categoryLabel}</b>
                      <small>
                        已匹配 {group.matchedCount}/{group.items.length} 个候选商品
                      </small>
                    </div>
                    <span
                      className={classNames(
                        "product-match-status",
                        isConfirmed && "done",
                      )}
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
                  {isExpanded && (
                    <div className="product-match-examples">
                      <div className="product-match-examples-heading">
                        <b>补充商品信息</b>
                        <span>可修改 Listing，并从系统品类规则中选择品类。</span>
                      </div>
                      <div className="product-match-editor-list">
                        {(showAll.has(group.key)
                          ? group.items
                          : group.items.slice(0, 3)
                        ).map((item) => {
                          const draft = drafts[productMatchKey(item)];
                          return (
                            <div
                              className="product-match-editor-row"
                              key={item.product_key}
                            >
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
                                  onChange={(event) => {
                                    const categoryA = event.target.value;
                                    const allowedBs = categoryBs(categoryA);
                                    updateDraft(item, {
                                      category_a: categoryA,
                                      category_b: allowedBs.includes(draft.category_b)
                                        ? draft.category_b
                                        : "",
                                    });
                                  }}
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
                                    updateDraft(item, {
                                      category_b: event.target.value,
                                    })
                                  }
                                  disabled={!draft.category_a}
                                >
                                  <option value="">请选择</option>
                                  {categoryBs(draft.category_a).map((category) => (
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
                        onClick={() =>
                          setShowAll((current) => {
                            const next = new Set(current);
                            if (next.has(group.key)) next.delete(group.key);
                            else next.add(group.key);
                            return next;
                          })
                        }
                      >
                        {showAll.has(group.key) ? "收起" : "查看全部"}{" "}
                        {group.items.length} 个销售 SKU
                        <CaretRight size={14} />
                      </button>
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        </section>
      </div>

      <footer className="product-match-footer">
        <div>
          <input
            type="checkbox"
            checked={groups.length > 0 && selected.size === groups.length}
            onChange={() =>
              setSelected(
                selected.size === groups.length
                  ? new Set()
                  : new Set(groups.map((group) => group.key)),
              )
            }
            aria-label="选择全部 Listing 组"
          />
          <span>
            已选择 <b>{selected.size}</b> 组 · 覆盖{" "}
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
            disabled={selected.size === 0}
            onClick={confirmSelected}
          >
            确认所选关联
          </button>
          <button
            type="button"
            className="primary-button"
            disabled={!allConfirmed || saving}
            onClick={save}
          >
            {saving ? "正在保存…" : "保存关联并重新生成计划"}
          </button>
        </div>
      </footer>
    </div>
  );
}
