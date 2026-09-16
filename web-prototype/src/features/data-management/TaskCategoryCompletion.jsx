import { useState } from "react";
import { api } from "../../api";

/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRecord} DatasetRecord */
/** @typedef {import("../task-create/taskCreateContracts").TaskRepairContext} TaskRepairContext */
/** @typedef {import("../task-create/taskCreateContracts").CategoryOption} CategoryOption */
/** @typedef {import("../task-create/taskCreateContracts").UnresolvedProduct} UnresolvedProduct */
/** @typedef {UnresolvedProduct & {listing: string, category_a: string, category_b: string, selected: boolean}} CompletionItem */
/** @typedef {Error & {status?: number}} DataRequestError */

/** @param {unknown} error @returns {DataRequestError} */
function requestError(error) {
  return error instanceof Error
    ? /** @type {DataRequestError} */ (error)
    : new Error("保存商品品类失败");
}

/**
 * @param {{
 *   dataset: DatasetRecord,
 *   focus: TaskRepairContext,
 *   notify: (message: string, tone?: string) => void,
 *   onReturnToTask?: (productVersionId: string) => void,
 * }} props
 */
export function TaskCategoryCompletion({ dataset, focus, notify, onReturnToTask }) {
  const categoryOptions = /** @type {CategoryOption[]} */ (focus.categoryOptions ?? []);
  const [items, setItems] = useState(
    /** @returns {CompletionItem[]} */ () =>
      (focus.unresolvedProducts ?? []).map((item) => ({
        ...item,
        listing: item.suggested_listing ?? "",
        category_a: "",
        category_b: "",
        selected: false,
      })),
  );
  const [listingFilter, setListingFilter] = useState("all");
  const [bulkCategory, setBulkCategory] = useState("");
  const [changeNote, setChangeNote] = useState(
    `补充任务“${focus.taskTitle || focus.store}”缺失的商品品类`,
  );
  const [saving, setSaving] = useState(false);
  const listingGroups = Array.from(
    new Set(items.map((item) => item.suggested_listing).filter(Boolean)),
  ).sort();
  const visibleItems = items.filter(
    (item) => listingFilter === "all" || item.suggested_listing === listingFilter,
  );
  const selectedCount = items.filter((item) => item.selected).length;
  const completedItems = items.filter(
    (item) => item.editable && item.listing && item.category_a && item.category_b,
  );
  const coveredComments = completedItems.reduce(
    (total, item) => total + Number(item.comment_count || 0),
    0,
  );

  /** @param {string} productKey @param {Partial<CompletionItem>} changes */
  const updateItem = (productKey, changes) => {
    setItems((current) =>
      current.map((item) =>
        item.product_key === productKey ? { ...item, ...changes } : item,
      ),
    );
  };
  const selectVisible = () => {
    const visibleKeys = new Set(
      visibleItems.filter((item) => item.editable).map((item) => item.product_key),
    );
    const allSelected = visibleItems
      .filter((item) => item.editable)
      .every((item) => item.selected);
    setItems((current) =>
      current.map((item) =>
        visibleKeys.has(item.product_key) ? { ...item, selected: !allSelected } : item,
      ),
    );
  };
  const applyBulkCategory = () => {
    const option = categoryOptions[Number(bulkCategory)];
    if (!option) return;
    setItems((current) =>
      current.map((item) =>
        item.selected
          ? {
              ...item,
              category_a: option.category_a,
              category_b: option.category_b,
              selected: false,
            }
          : item,
      ),
    );
    setBulkCategory("");
  };
  const save = async () => {
    if (!completedItems.length || !changeNote.trim()) return;
    setSaving(true);
    try {
      const result = await api.completeProductCategories(dataset.id, {
        expected_version: dataset.current_version,
        store: focus.store,
        items: completedItems.map((item) => ({
          msku: item.msku,
          listing: item.listing,
          category_a: item.category_a,
          category_b: item.category_b,
          product_name: item.product_name || "",
        })),
        change_note: changeNote.trim(),
      });
      const versionId = result.versions?.find(
        (version) => version.version === result.current_version,
      )?.id;
      notify(
        `已补充 ${completedItems.length} 个商品，并创建产品信息 v${result.current_version}`,
      );
      if (versionId) onReturnToTask?.(versionId);
    } catch (error) {
      const nextError = requestError(error);
      notify(
        nextError.status === 409
          ? "产品信息已被其他用户修改，请刷新后重新提交"
          : nextError.message,
        "error",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="task-category-completion" aria-label="当前任务待补充商品">
      <header>
        <div>
          <span>当前任务待补充</span>
          <h3>{focus.taskTitle || "待创建分析任务"}</h3>
          <p>这里只显示阻断当前任务的商品，不需要在完整产品信息中搜索。</p>
        </div>
        <div className="completion-stats">
          <span>
            <small>待补充商品</small>
            <strong>{items.length}</strong>
          </span>
          <span>
            <small>已填写商品</small>
            <strong>{completedItems.length}</strong>
          </span>
          <span>
            <small>覆盖阻断评论</small>
            <strong>
              {coveredComments}/{focus.blockedCommentCount ?? 0}
            </strong>
          </span>
        </div>
      </header>
      <div className="completion-toolbar">
        <label>
          按 Listing 分组
          <select
            value={listingFilter}
            onChange={(event) => setListingFilter(event.target.value)}
          >
            <option value="all">全部商品（{items.length}）</option>
            {listingGroups.map((listing) => (
              <option key={listing} value={listing}>
                {listing}（
                {items.filter((item) => item.suggested_listing === listing).length}）
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="secondary-button" onClick={selectVisible}>
          选择当前 {visibleItems.length} 个
        </button>
        <label className="completion-category-select">
          批量设置品类
          <select
            value={bulkCategory}
            onChange={(event) => setBulkCategory(event.target.value)}
          >
            <option value="">选择品类A / 品类B</option>
            {categoryOptions.map((option, index) => (
              <option key={`${option.category_a}-${option.category_b}`} value={index}>
                {option.category_a} / {option.category_b}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="primary-button"
          disabled={!selectedCount || bulkCategory === ""}
          onClick={applyBulkCategory}
        >
          应用到已选 {selectedCount} 个
        </button>
      </div>
      <div className="completion-table">
        <div className="table-head">
          <span>选择</span>
          <span>商品 / 问题</span>
          <span>Listing</span>
          <span>品类A / 品类B</span>
          <span>影响</span>
        </div>
        {visibleItems.map((item) => {
          const categoryIndex = categoryOptions.findIndex(
            (option) =>
              option.category_a === item.category_a &&
              option.category_b === item.category_b,
          );
          return (
            <div key={item.product_key}>
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
                    <option
                      key={`${option.category_a}-${option.category_b}`}
                      value={index}
                    >
                      {option.category_a} / {option.category_b}
                    </option>
                  ))}
                </select>
              </span>
              <span>
                <strong>{item.comment_count} 条评论</strong>
                <small>{item.record_count} 条记录</small>
              </span>
            </div>
          );
        })}
      </div>
      <footer className="completion-footer">
        <label>
          修改原因
          <input
            value={changeNote}
            onChange={(event) => setChangeNote(event.target.value)}
          />
        </label>
        <button
          type="button"
          className="primary-button"
          disabled={!completedItems.length || !changeNote.trim() || saving}
          onClick={save}
        >
          {saving
            ? "正在创建新版本…"
            : `保存 ${completedItems.length} 个商品并重新预检`}
        </button>
      </footer>
    </section>
  );
}
