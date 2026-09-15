const FALLBACK_LISTING = "待补充 Listing";
const VALUE_SEPARATOR = "\u001f";

/**
 * @param {...(string | undefined)} values
 */
function firstNonEmpty(...values) {
  return values.find(Boolean) ?? "";
}

/**
 * @typedef {Object} ProductCategoryOption
 * @property {string} category_a
 * @property {string} category_b
 */

/**
 * @typedef {Object} ProductMatchCandidate
 * @property {string=} store
 * @property {string=} msku
 * @property {string=} listing
 * @property {string=} category_a
 * @property {string=} category_b
 * @property {string=} product_name
 * @property {number=} match_score
 */

/**
 * @typedef {Object} ProductMatchItem
 * @property {string} product_key
 * @property {string=} store
 * @property {string} msku
 * @property {string=} suggested_listing
 * @property {number=} record_count
 * @property {number=} comment_count
 * @property {boolean=} editable
 * @property {string=} match_status
 * @property {ProductMatchCandidate=} match_candidate
 * @property {string=} current_category_a
 * @property {string=} current_category_b
 * @property {string=} product_name
 */

/**
 * @typedef {Object} ProductMatchDraft
 * @property {string} store
 * @property {string} msku
 * @property {string} listing
 * @property {string} category_a
 * @property {string} category_b
 * @property {string} product_name
 */

/**
 * @typedef {Object} ProductMatchGroup
 * @property {string} key
 * @property {string} store
 * @property {string} listing
 * @property {ProductMatchItem[]} items
 * @property {number} commentCount
 * @property {number} recordCount
 * @property {number} matchedCount
 * @property {number} needsReview
 * @property {boolean} ready
 * @property {string} categoryLabel
 */

/**
 * @typedef {Object} ProductMatchPlan
 * @property {ProductMatchItem[]=} unresolved_products
 * @property {ProductCategoryOption[]=} category_options
 * @property {number=} unresolved_product_comment_count
 * @property {number=} blocked_count
 */

/**
 * @param {ProductMatchItem} item
 */
export function productMatchKey(item) {
  return `${item.store}${VALUE_SEPARATOR}${item.msku}`;
}

/**
 * @param {ProductMatchItem} item
 */
export function productMatchGroupKey(item) {
  const listing =
    item.suggested_listing || item.match_candidate?.listing || FALLBACK_LISTING;
  return `${item.store}${VALUE_SEPARATOR}${listing}`;
}

/**
 * @param {ProductMatchItem[]} items
 */
export function editableProductMatchItems(items) {
  return items.filter((item) => item.editable && item.store);
}

/**
 * @param {ProductMatchItem} item
 * @returns {ProductMatchDraft}
 */
export function initialProductMatch(item) {
  const candidate = item.match_candidate ?? {};
  return {
    store: firstNonEmpty(item.store, candidate.store),
    msku: item.msku,
    listing: firstNonEmpty(candidate.listing, item.suggested_listing),
    category_a: firstNonEmpty(candidate.category_a, item.current_category_a),
    category_b: firstNonEmpty(candidate.category_b, item.current_category_b),
    product_name: firstNonEmpty(candidate.product_name, item.product_name),
  };
}

/**
 * @param {ProductMatchItem[]} items
 * @returns {Record<string, ProductMatchDraft>}
 */
export function buildInitialProductMatchDrafts(items) {
  return Object.fromEntries(
    items.map((item) => [productMatchKey(item), initialProductMatch(item)]),
  );
}

/**
 * @param {ProductMatchDraft | undefined} draft
 */
function productMatchIsReady(draft) {
  return Boolean(draft?.store && draft.listing && draft.category_a && draft.category_b);
}

/**
 * @param {ProductMatchItem[]} items
 * @param {Record<string, ProductMatchDraft>} drafts
 * @returns {ProductMatchGroup[]}
 */
export function buildProductMatchGroups(items, drafts) {
  /** @type {Map<string, ProductMatchGroup>} */
  const groups = new Map();

  items.forEach((item) => {
    const listing =
      item.suggested_listing || item.match_candidate?.listing || FALLBACK_LISTING;
    const key = productMatchGroupKey(item);
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        store: item.store || "",
        listing,
        items: [],
        commentCount: 0,
        recordCount: 0,
        matchedCount: 0,
        needsReview: 0,
        ready: false,
        categoryLabel: "",
      });
    }

    const group = groups.get(key);
    if (!group) return;
    group.items.push(item);
    group.commentCount += Number(item.comment_count || 0);
    group.recordCount += Number(item.record_count || 0);
  });

  return Array.from(groups.values())
    .map((group) => {
      const matchedDrafts = group.items
        .map((item) => drafts[productMatchKey(item)])
        .filter(productMatchIsReady);
      const categories = new Set(
        matchedDrafts.map(
          (draft) => `${draft.category_a}${VALUE_SEPARATOR}${draft.category_b}`,
        ),
      );

      return {
        ...group,
        matchedCount: matchedDrafts.length,
        needsReview: group.items.filter(
          (item) => item.match_status !== "high_confidence",
        ).length,
        ready: matchedDrafts.length === group.items.length,
        categoryLabel:
          categories.size === 1
            ? Array.from(categories)[0].split(VALUE_SEPARATOR).join(" > ")
            : `${categories.size} 种品类规则`,
      };
    })
    .sort((left, right) => right.commentCount - left.commentCount);
}

/**
 * @param {ProductCategoryOption[]} options
 */
export function buildProductCategoryOptions(options) {
  const categoryAs = Array.from(new Set(options.map((item) => item.category_a))).sort();
  const categoryBsByA = Object.fromEntries(
    categoryAs.map((categoryA) => [
      categoryA,
      options
        .filter((item) => item.category_a === categoryA)
        .map((item) => item.category_b),
    ]),
  );
  return { categoryAs, categoryBsByA };
}

/**
 * @param {ProductMatchGroup[]} groups
 * @param {string} filter
 */
export function filterProductMatchGroups(groups, filter) {
  if (filter === "high") {
    return groups.filter((group) => group.needsReview === 0);
  }
  if (filter === "review") {
    return groups.filter((group) => group.needsReview > 0);
  }
  return groups;
}

/**
 * @param {ProductMatchGroup[]} groups
 * @param {Record<string, ProductMatchDraft>} drafts
 * @returns {ProductMatchDraft[]}
 */
export function buildProductMatchSaveItems(groups, drafts) {
  return groups.flatMap((group) =>
    group.items.map((item) => drafts[productMatchKey(item)]),
  );
}

/**
 * @param {unknown} value
 */
export function displayProductText(value) {
  return String(value || "").replaceAll("&amp;", "&");
}
