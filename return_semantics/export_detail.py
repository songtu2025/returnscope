from __future__ import annotations

from return_semantics.data import ReturnDataset
from return_semantics.export_formatting import (
    _display_key,
    _format_labels,
    _format_relations,
)
from return_semantics.schemas import (
    ProcessingStatus,
    TaxonomyConfig,
    ValidatedClassification,
)
from return_semantics.taxonomy_hierarchy import label_path


def _build_detail_rows(
    dataset: ReturnDataset,
    results: dict[str, ValidatedClassification],
    taxonomy: TaxonomyConfig,
) -> list[dict[str, object]]:
    label_names = {label.code: label.name for label in taxonomy.labels}
    rows = []
    for record in dataset.records.to_dict(orient="records"):
        if not record.get("category_a") or not record.get("category_b"):
            result = None
            status = "EXCLUDED_MISSING_CATEGORY"
        elif not record["has_text_evidence"]:
            result = None
            status = ProcessingStatus.NO_TEXT_EVIDENCE.value
        else:
            result = results.get(record["classification_key"])
            status = result.status.value if result is not None else "PENDING"

        units = result.semantic_units if result is not None else []
        rows.append(
            {
                "源数据行号": record["source_row"],
                "分类键": _display_key(record["classification_key"]),
                "return-date": record["return-date"],
                "order-id": record["order-id"],
                "sku": record.get("source_sku", record.get("sku_raw", "")),
                "source_sku": record.get("source_sku", record.get("sku_raw", "")),
                "matched_msku": record.get("matched_msku", ""),
                "product_sku": record.get("product_sku", ""),
                "asin": record["asin"],
                "店铺/站点": record.get("store", ""),
                "Listing": record.get("listing", ""),
                "产品名称": record.get("product_name", ""),
                "商品匹配状态": record.get("product_match_status", "unmatched"),
                "品类A": record.get("category_a", ""),
                "品类B": record.get("category_b", ""),
                "Amazon原因": record["reason"],
                "评论原文": record["comment_raw"],
                "标准化评论": record["comment_normalized"],
                "问题标签": _format_labels(
                    result.problem_label_codes if result else [],
                    label_names,
                ),
                "正面标签": _format_labels(
                    result.positive_label_codes if result else [],
                    label_names,
                ),
                "主因标签": _format_labels(
                    result.primary_label_codes if result else [],
                    label_names,
                ),
                "完整标签路径": " | ".join(
                    " → ".join(label_path(taxonomy, unit.label_code)) for unit in units
                ),
                "事实编号": " | ".join(
                    ",".join(unit.fact_ids or ([unit.fact_id] if unit.fact_id else []))
                    for unit in units
                ),
                "使用者引用": " | ".join(unit.actor_ref for unit in units),
                "观点来源引用": " | ".join(unit.source_ref for unit in units),
                "实际体验者引用": " | ".join(unit.experiencer_ref for unit in units),
                "商品引用": " | ".join(unit.product_ref for unit in units),
                "规格引用": " | ".join(unit.variant_ref for unit in units),
                "事件引用": " | ".join(unit.event_ref for unit in units),
                "比较基准": " | ".join(unit.reference_basis.value for unit in units),
                "陈述类型": " | ".join(unit.statement_type for unit in units),
                "事实角色": " | ".join(unit.fact_role.value for unit in units),
                "操作": " | ".join(unit.operation for unit in units),
                "条件": " | ".join(unit.condition for unit in units),
                "部位": " | ".join(unit.part for unit in units),
                "因果归属": " | ".join(unit.causal_attribution.value for unit in units),
                "因果说明": " | ".join(
                    unit.causal_attribution_reason for unit in units
                ),
                "判定理由": " | ".join(unit.decision_reason for unit in units),
                "证据原文": " | ".join(unit.evidence for unit in units),
                "证据来源": " | ".join(unit.evidence_source.value for unit in units),
                "未映射处置": " | ".join(
                    item.disposition.value
                    for item in (result.unknown_semantics if result else [])
                ),
                "评论摘要状态": (result.comment_summary.status.value if result else ""),
                "语义关系": _format_relations(result) if result else "",
                "Listing承诺关系": " | ".join(
                    unit.claim_relation.value for unit in units
                ),
                "Listing承诺编号": " | ".join(unit.claim_id or "" for unit in units),
                "处理状态": status,
                "复核原因": " | ".join(result.review_reasons if result else []),
                "模型": result.model_name if result else "",
                "提示版本": result.prompt_version if result else "",
                "分类体系版本": result.taxonomy_version if result else "",
            }
        )
    return rows
