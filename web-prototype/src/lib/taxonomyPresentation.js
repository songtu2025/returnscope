export function taxonomyPath(taxonomy, node) {
  if (node.label_path?.length) return node.label_path;
  if (taxonomy?.structure_version !== 2) return [node.group, node.name].filter(Boolean);
  const categories = new Map(
    (taxonomy.categories ?? []).map((item) => [item.code, item]),
  );
  const path = [node.name];
  const visited = new Set([node.code]);
  let parent = categories.get(node.parent_code);
  while (parent && !visited.has(parent.code)) {
    visited.add(parent.code);
    path.unshift(parent.name);
    parent = categories.get(parent.parent_code);
  }
  return path.filter(Boolean);
}

export function labelText(label) {
  return label.label_path?.length
    ? label.label_path.join(" → ")
    : label.name || label.code;
}

export function resultLabelText(record, codes = []) {
  return codes
    .map((code) => record.problem_label_paths?.[code]?.join(" → ") || code)
    .join("、");
}
