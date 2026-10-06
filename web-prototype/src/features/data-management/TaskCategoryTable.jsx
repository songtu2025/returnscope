/** @typedef {import("./TaskCategoryCompletion").CompletionItem} CompletionItem */
/** @typedef {import("../task-create/taskCreateContracts").CategoryOption} CategoryOption */
/** @typedef {(productKey: string, changes: Partial<CompletionItem>) => void} UpdateItem */

/** @param {{visibleItems: CompletionItem[], categoryOptions: CategoryOption[], updateItem: UpdateItem}} props */
export function TaskCategoryTable({ visibleItems, categoryOptions, updateItem }) {
  return (
    <div className="completion-table">
      <div className="table-head">
        <span>选择</span>
        <span>商品 / 问题</span>
        <span>Listing</span>
        <span>品类A / 品类B</span>
        <span>影响</span>
      </div>
      {visibleItems.map((item) => (
        <CompletionRow
          key={item.product_key}
          item={item}
          categoryOptions={categoryOptions}
          updateItem={updateItem}
        />
      ))}
    </div>
  );
}

/** @param {{item: CompletionItem, categoryOptions: CategoryOption[], updateItem: UpdateItem}} props */
function CompletionRow({ item, categoryOptions, updateItem }) {
  const categoryIndex = categoryOptions.findIndex(
    (option) =>
      option.category_a === item.category_a && option.category_b === item.category_b,
  );
  return (
    <div>
      <span>
        <input
          type="checkbox"
          aria-label={`选择 ${item.msku || "缺失 SKU"}`}
          checked={item.selected}
          disabled={!item.editable}
          onChange={(event) =>
            updateItem(item.product_key, { selected: event.target.checked })
          }
        />
      </span>
      <CompletionProductDescription item={item} />
      <span>
        <input
          aria-label={`${item.msku} Listing`}
          value={item.listing}
          disabled={!item.editable}
          onChange={(event) =>
            updateItem(item.product_key, { listing: event.target.value })
          }
        />
      </span>
      <CompletionCategorySelect
        item={item}
        categoryOptions={categoryOptions}
        categoryIndex={categoryIndex}
        updateItem={updateItem}
      />
      <span>
        <strong>{item.comment_count} 条评论</strong>
        <small>{item.record_count} 条记录</small>
      </span>
    </div>
  );
}

/** @param {{item: CompletionItem, categoryOptions: CategoryOption[], categoryIndex: number, updateItem: UpdateItem}} props */
function CompletionCategorySelect({
  item,
  categoryOptions,
  categoryIndex,
  updateItem,
}) {
  return (
    <span>
      <select
        aria-label={`${item.msku} 品类`}
        value={categoryIndex >= 0 ? String(categoryIndex) : ""}
        disabled={!item.editable}
        onChange={(event) => {
          const option =
            event.target.value === ""
              ? null
              : categoryOptions[Number(event.target.value)];
          updateItem(item.product_key, {
            category_a: option?.category_a ?? "",
            category_b: option?.category_b ?? "",
          });
        }}
      >
        <option value="">待选择</option>
        {categoryOptions.map((option, index) => (
          <option key={`${option.category_a}-${option.category_b}`} value={index}>
            {option.category_a} / {option.category_b}
          </option>
        ))}
      </select>
    </span>
  );
}

/** @param {{item: CompletionItem}} props */
function CompletionProductDescription({ item }) {
  return (
    <span>
      <code>{item.msku || "缺失 SKU"}</code>
      <small>{item.product_name || "暂无商品名称"}</small>
      <em>
        {item.issue === "product_not_found"
          ? "产品信息中不存在，将新增"
          : item.issue === "missing_category"
            ? "商品已存在，品类为空"
            : item.issue === "unsupported_category"
              ? "当前品类未配置分类逻辑"
              : "缺少商品标识，需修正退货源数据"}
      </em>
    </span>
  );
}
