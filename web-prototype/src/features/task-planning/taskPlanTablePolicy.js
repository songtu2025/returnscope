/** @typedef {import("./taskPlanContracts").TaskPlanSegment} TaskPlanSegment */
/** @param {TaskPlanSegment} item */
export const listingKey = (item) =>
  JSON.stringify(
    item.scope ? [item.scope.store, item.scope.listing] : item.segment_key,
  );

/** @param {TaskPlanSegment[]} segments @param {{query: string, category: string, status: string}} filters */
export function filterPlanSegments(segments, filters) {
  const query = filters.query.trim().toLocaleLowerCase();
  return segments.filter(
    (item) =>
      (!filters.status || item.status === filters.status) &&
      (!filters.category ||
        item.variants.some(
          (variant) =>
            `${variant.category_a} / ${variant.category_b}` === filters.category,
        )) &&
      (!query ||
        [
          item.scope?.listing,
          item.scope?.store,
          item.standard_name,
          item.agent_family,
          ...item.variants.flatMap((variant) => [
            variant.category_a,
            variant.category_b,
          ]),
        ]
          .join(" ")
          .toLocaleLowerCase()
          .includes(query)),
  );
}

/** @param {string[]} full @param {string[]} visible @param {string[]} next */
export function applyVisibleOrder(full, visible, next) {
  const replacements = next[Symbol.iterator]();
  return full.map((key) =>
    visible.includes(key) ? (replacements.next().value ?? key) : key,
  );
}

/** @param {TaskPlanSegment[]} segments @param {number} page @param {number} pageSize */
export function paginatePlanListings(segments, page, pageSize) {
  const listings = [...new Set(segments.map(listingKey))];
  const totalPages = Math.max(1, Math.ceil(listings.length / pageSize));
  const current = Math.min(page, totalPages);
  const pageKeys = new Set(
    listings.slice((current - 1) * pageSize, current * pageSize),
  );
  return {
    page: current,
    total: listings.length,
    totalPages,
    items: segments.filter((item) => pageKeys.has(listingKey(item))),
  };
}

/** @param {string[]} current @param {TaskPlanSegment[]} candidates @param {boolean} selected */
export function selectPlanSegments(current, candidates, selected) {
  const keys = new Set(candidates.map((item) => item.segment_key));
  return selected
    ? [...new Set([...current, ...keys])]
    : current.filter((key) => !keys.has(key));
}
