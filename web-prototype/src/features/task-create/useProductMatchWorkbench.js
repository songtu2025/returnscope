import { useMemo, useState } from "react";

import {
  buildInitialProductMatchDrafts,
  buildProductCategoryOptions,
  buildProductMatchGroups,
  buildProductMatchSaveItems,
  editableProductMatchItems,
  filterProductMatchGroups,
  productMatchGroupKey,
  productMatchKey,
} from "./productMatchPolicy";

/**
 * @param {Set<string>} current
 * @param {string} key
 */
function toggledSet(current, key) {
  const next = new Set(current);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  return next;
}

/**
 * @param {import("./productMatchPolicy").ProductMatchPlan} plan
 */
export function useProductMatchWorkbench(plan) {
  const sourceItems = useMemo(
    () => editableProductMatchItems(plan.unresolved_products ?? []),
    [plan.unresolved_products],
  );
  const [drafts, setDrafts] = useState(() =>
    buildInitialProductMatchDrafts(sourceItems),
  );
  const groups = useMemo(
    () => buildProductMatchGroups(sourceItems, drafts),
    [drafts, sourceItems],
  );
  const categoryOptions = useMemo(
    () => buildProductCategoryOptions(plan.category_options ?? []),
    [plan.category_options],
  );
  const [filter, setFilter] = useState("all");
  const [selectedGroupKeys, setSelectedGroupKeys] = useState(
    () => /** @type {Set<string>} */ (new Set()),
  );
  const [selectedProductKeys, setSelectedProductKeys] = useState(
    () => /** @type {Set<string>} */ (new Set()),
  );
  const [confirmedGroupKeys, setConfirmedGroupKeys] = useState(
    () => /** @type {Set<string>} */ (new Set()),
  );
  const [expandedGroupKey, setExpandedGroupKey] = useState(groups[0]?.key ?? "");
  const [showAllGroupKeys, setShowAllGroupKeys] = useState(
    () => /** @type {Set<string>} */ (new Set()),
  );
  const [bulkCategoryA, setBulkCategoryA] = useState("");
  const [bulkCategoryB, setBulkCategoryB] = useState("");

  const visibleGroups = useMemo(
    () => filterProductMatchGroups(groups, filter),
    [filter, groups],
  );
  const selectedGroups = groups.filter((group) => selectedGroupKeys.has(group.key));
  const confirmedComments = groups
    .filter((group) => confirmedGroupKeys.has(group.key))
    .reduce((total, group) => total + group.commentCount, 0);
  const selectedComments = selectedGroups.reduce(
    (total, group) => total + group.commentCount,
    0,
  );
  const readyGroupCount = groups.filter((group) => group.ready).length;
  const highConfidenceGroupCount = groups.filter(
    (group) => group.needsReview === 0,
  ).length;
  const selectedProductCount = selectedProductKeys.size;
  const allConfirmed =
    readyGroupCount === groups.length && confirmedGroupKeys.size === groups.length;
  const saveItems = useMemo(
    () => buildProductMatchSaveItems(groups, drafts),
    [drafts, groups],
  );

  /**
   * @param {string} groupKey
   */
  const toggleSelectedGroup = (groupKey) => {
    setSelectedGroupKeys((current) => toggledSet(current, groupKey));
  };

  /**
   * @param {string} groupKey
   */
  const confirmGroup = (groupKey) => {
    setConfirmedGroupKeys((current) => new Set(current).add(groupKey));
  };

  const confirmSelectedGroups = () => {
    setConfirmedGroupKeys((current) => {
      const next = new Set(current);
      selectedGroups
        .filter((group) => group.ready)
        .forEach((group) => next.add(group.key));
      return next;
    });
  };

  /**
   * @param {import("./productMatchPolicy").ProductMatchItem} item
   * @param {Partial<import("./productMatchPolicy").ProductMatchDraft>} changes
   */
  const updateDraft = (item, changes) => {
    const itemKey = productMatchKey(item);
    setDrafts((current) => ({
      ...current,
      [itemKey]: { ...current[itemKey], ...changes },
    }));
    const groupKey = productMatchGroupKey(item);
    setConfirmedGroupKeys((current) => {
      const next = new Set(current);
      next.delete(groupKey);
      return next;
    });
  };

  /**
   * @param {string} itemKey
   */
  const toggleProductSelected = (itemKey) => {
    setSelectedProductKeys((current) => toggledSet(current, itemKey));
  };

  /**
   * @param {import("./productMatchPolicy").ProductMatchGroup} group
   */
  const toggleGroupProducts = (group) => {
    const itemKeys = group.items.map(productMatchKey);
    setSelectedProductKeys((current) => {
      const next = new Set(current);
      const allSelected = itemKeys.every((itemKey) => current.has(itemKey));
      itemKeys.forEach((itemKey) =>
        allSelected ? next.delete(itemKey) : next.add(itemKey),
      );
      return next;
    });
  };

  const applyBulkCategories = () => {
    if (!selectedProductCount || !bulkCategoryA || !bulkCategoryB) return;
    const selectedItems = sourceItems.filter((item) =>
      selectedProductKeys.has(productMatchKey(item)),
    );
    setDrafts((current) => {
      const next = { ...current };
      selectedItems.forEach((item) => {
        const itemKey = productMatchKey(item);
        next[itemKey] = {
          ...next[itemKey],
          category_a: bulkCategoryA,
          category_b: bulkCategoryB,
        };
      });
      return next;
    });
    const affectedGroupKeys = new Set(selectedItems.map(productMatchGroupKey));
    setConfirmedGroupKeys((current) => {
      const next = new Set(current);
      affectedGroupKeys.forEach((groupKey) => next.delete(groupKey));
      return next;
    });
    setSelectedProductKeys(new Set());
  };

  /**
   * @param {string} categoryA
   */
  const selectBulkCategoryA = (categoryA) => {
    const allowedCategoryBs = categoryOptions.categoryBsByA[categoryA] ?? [];
    setBulkCategoryA(categoryA);
    setBulkCategoryB((current) => (allowedCategoryBs.includes(current) ? current : ""));
  };

  /**
   * @param {import("./productMatchPolicy").ProductMatchItem} item
   * @param {string} categoryA
   */
  const selectDraftCategoryA = (item, categoryA) => {
    const allowedCategoryBs = categoryOptions.categoryBsByA[categoryA] ?? [];
    const draft = drafts[productMatchKey(item)];
    updateDraft(item, {
      category_a: categoryA,
      category_b: allowedCategoryBs.includes(draft.category_b) ? draft.category_b : "",
    });
  };

  /**
   * @param {string} groupKey
   */
  const toggleExpandedGroup = (groupKey) => {
    setExpandedGroupKey((current) => (current === groupKey ? "" : groupKey));
  };

  /**
   * @param {string} groupKey
   */
  const toggleShowAll = (groupKey) => {
    setShowAllGroupKeys((current) => toggledSet(current, groupKey));
  };

  const toggleAllGroups = () => {
    setSelectedGroupKeys((current) =>
      current.size === groups.length
        ? new Set()
        : new Set(groups.map((group) => group.key)),
    );
  };

  /**
   * @param {string} categoryB
   */
  const selectBulkCategoryB = (categoryB) => {
    setBulkCategoryB(categoryB);
  };

  /**
   * @param {string} nextFilter
   */
  const selectFilter = (nextFilter) => {
    setFilter(nextFilter);
  };

  return {
    allConfirmed,
    bulkCategoryA,
    bulkCategoryB,
    categoryAs: categoryOptions.categoryAs,
    categoryBsByA: categoryOptions.categoryBsByA,
    confirmedComments,
    confirmedGroupKeys,
    drafts,
    expandedGroupKey,
    filter,
    groups,
    highConfidenceGroupCount,
    reviewGroupCount: groups.length - highConfidenceGroupCount,
    saveItems,
    selectedComments,
    selectedGroupKeys,
    selectedProductCount,
    selectedProductKeys,
    showAllGroupKeys,
    visibleGroups,
    applyBulkCategories,
    clearSelectedProducts: () => setSelectedProductKeys(new Set()),
    confirmGroup,
    confirmSelectedGroups,
    selectBulkCategoryA,
    selectBulkCategoryB,
    selectDraftCategoryA,
    selectFilter,
    toggleAllGroups,
    toggleExpandedGroup,
    toggleGroupProducts,
    toggleProductSelected,
    toggleSelectedGroup,
    toggleShowAll,
    updateDraft,
  };
}
