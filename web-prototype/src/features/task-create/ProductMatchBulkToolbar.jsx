/**
 * @param {{workbench: ReturnType<typeof import("./useProductMatchWorkbench").useProductMatchWorkbench>}} props
 */
export function ProductMatchBulkToolbar({ workbench }) {
  const {
    applyBulkCategories,
    bulkCategoryA,
    bulkCategoryB,
    categoryAs,
    categoryBsByA,
    clearSelectedProducts,
    selectBulkCategoryA,
    selectBulkCategoryB,
    selectedProductCount,
  } = workbench;

  return (
    <section className="product-match-bulk-toolbar" aria-label="批量修改商品品类">
      <div className="product-match-bulk-summary">
        <b>批量修改商品品类</b>
        <span>
          已选择 {selectedProductCount} 个销售 SKU；应用后需重新确认对应 Listing。
        </span>
      </div>
      <label>
        品类A
        <select
          aria-label="批量品类A"
          disabled={!selectedProductCount}
          value={bulkCategoryA}
          onChange={(event) => selectBulkCategoryA(event.target.value)}
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
          aria-label="批量品类B"
          disabled={!selectedProductCount || !bulkCategoryA}
          value={bulkCategoryB}
          onChange={(event) => selectBulkCategoryB(event.target.value)}
        >
          <option value="">请选择</option>
          {(categoryBsByA[bulkCategoryA] ?? []).map((category) => (
            <option key={category} value={category}>
              {category}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className="primary-button"
        disabled={!selectedProductCount || !bulkCategoryA || !bulkCategoryB}
        onClick={applyBulkCategories}
      >
        应用到 {selectedProductCount} 个商品
      </button>
      <button
        type="button"
        className="secondary-button"
        disabled={!selectedProductCount}
        onClick={clearSelectedProducts}
      >
        清空选择
      </button>
    </section>
  );
}
