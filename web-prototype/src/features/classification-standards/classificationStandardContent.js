import { groups as BUSINESS_GROUPS } from "../../../../config/taxonomy_alignment.json";

export const cloneClassificationStandardContent = (value) =>
  JSON.parse(JSON.stringify(value));

export const EMPTY_CLASSIFICATION_STANDARD_CONTENT = {
  recognition_profile: "semantic_v1",
  name: "",
  product_context: "",
  instructions: ["依据标签名称、完整路径和补充判定说明判断退货原因"],
  allowed_parts: ["UNSPECIFIED"],
  validation_rules: {
    allowed_groups: BUSINESS_GROUPS,
    neutral_reason_labels: [],
    conflict_scope: "evidence",
  },
  variants: [{ category_a: "", category_b: "", attributes: {} }],
  labels: [],
};

export function contentFromClassificationStandardSnapshot(snapshot) {
  return {
    name: snapshot.name,
    recognition_profile: snapshot.taxonomy.recognition_profile ?? "legacy_v3",
    product_context: snapshot.taxonomy.product_context,
    instructions: snapshot.taxonomy.instructions ?? [],
    allowed_parts: snapshot.taxonomy.allowed_parts ?? ["UNSPECIFIED"],
    validation_rules: snapshot.taxonomy.validation_rules ?? {},
    variants: snapshot.variants ?? [],
    ...(snapshot.taxonomy.structure_version === 2
      ? {
          structure_version: 2,
          categories: snapshot.taxonomy.categories ?? [],
          import_sources: snapshot.import_sources ?? [],
        }
      : {}),
    labels: (snapshot.taxonomy.labels ?? []).map((label) => ({
      ...label,
      keywords: label.keywords ?? [],
    })),
  };
}

export function validateClassificationStandardContent(content) {
  if (!content.name.trim() || !content.product_context.trim()) {
    return "请填写标准名称和适用商品说明";
  }
  if (
    content.variants.length === 0 ||
    content.variants.some((item) => !item.category_a.trim() || !item.category_b.trim())
  ) {
    return "请完整填写适用品类";
  }
  if (content.labels.length === 0) return "请至少增加一个分类标签";
  if (
    content.labels.some(
      (item) =>
        !item.code.trim() ||
        !item.name.trim() ||
        (content.structure_version === 2 ? !item.parent_code : !item.group.trim()),
    )
  ) {
    return "请完整填写标签所属分类、名称和编码";
  }
  return "";
}

export function classificationStandardContentFieldErrors(content) {
  return {
    name: content.name.trim() ? "" : "请填写标准名称",
    product_context: content.product_context.trim() ? "" : "请填写适用商品说明",
    variants: content.variants.map((item) => ({
      category_a: item.category_a.trim() ? "" : "请填写品类 A",
      category_b: item.category_b.trim() ? "" : "请填写品类 B",
    })),
    variants_empty: content.variants.length ? "" : "请至少增加一个适用品类",
    labels: content.labels.map((item) => ({
      name: item.name.trim() ? "" : "请填写标签名称",
      group: item.group.trim() ? "" : "请选择标签分组",
      code: item.code.trim() ? "" : "请填写标签编码",
    })),
    labels_empty: content.labels.length ? "" : "请至少增加一个分类标签",
  };
}

export function clearClassificationStandardContentFieldError(errors, field) {
  if (!field) return errors;
  if (!field.includes(".")) return { ...errors, [field]: "" };
  const [collection, indexText, key] = field.split(".");
  const index = Number(indexText);
  return {
    ...errors,
    [collection]: (errors[collection] ?? []).map((item, itemIndex) =>
      itemIndex === index ? { ...item, [key]: "" } : item,
    ),
  };
}
