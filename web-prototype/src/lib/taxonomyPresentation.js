/** @typedef {{code: string, name?: string, group?: string, parent_code?: string | null, label_path?: string[]}} TaxonomyNode */
/** @typedef {{structure_version?: number, categories?: TaxonomyNode[]}} Taxonomy */

/** @param {Taxonomy | null | undefined} taxonomy @param {TaxonomyNode} node @returns {string[]} */
export function taxonomyPath(taxonomy, node) {
  if (node.label_path?.length) return node.label_path;
  if (taxonomy?.structure_version !== 2) {
    const simplePath = [];
    if (node.group) simplePath.push(node.group);
    if (node.name) simplePath.push(node.name);
    return simplePath;
  }
  const categories = new Map(
    (taxonomy.categories ?? []).map((item) => [item.code, item]),
  );
  const path = node.name ? [node.name] : [];
  const visited = new Set([node.code]);
  let parent = node.parent_code ? categories.get(node.parent_code) : undefined;
  while (parent && !visited.has(parent.code)) {
    visited.add(parent.code);
    if (parent.name) path.unshift(parent.name);
    parent = parent.parent_code ? categories.get(parent.parent_code) : undefined;
  }
  return path.filter(Boolean);
}

/** @param {TaxonomyNode} label */
export function labelText(label) {
  return label.label_path?.length
    ? label.label_path.join(" → ")
    : label.name || label.code;
}

/** @param {unknown} record @param {string[]} [codes] */
export function resultLabelText(record, codes = []) {
  const paths =
    typeof record === "object" &&
    record !== null &&
    "problem_label_paths" in record &&
    typeof record.problem_label_paths === "object" &&
    record.problem_label_paths !== null
      ? /** @type {Record<string, string[]>} */ (record.problem_label_paths)
      : {};
  return codes.map((code) => paths[code]?.join(" → ") || code).join("、");
}
