from __future__ import annotations

from collections.abc import Hashable
from typing import Any

from return_semantics.data import ReturnDataset
from return_semantics.export_formatting import (
    _display_key,
    _format_labels,
    _format_relations,
)
from return_semantics.schemas import (
    ProcessingStatus,
    SemanticUnit,
    TaxonomyConfig,
    ValidatedClassification,
)
from return_semantics.taxonomy_hierarchy import label_path


def _source_detail_columns(record: dict[Hashable, Any]) -> dict[str, object]:
    return {
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
    }


def _classification_detail_columns(
    result: ValidatedClassification | None,
    units: list[SemanticUnit],
    taxonomy: TaxonomyConfig,
    label_names: dict[str, str],
) -> dict[str, object]:
    return {
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
    }


def _join_unit_field(
    units: list[SemanticUnit], field: str, *, enum_value: bool = False
) -> str:
    return " | ".join(
        getattr(unit, field).value if enum_value else getattr(unit, field)
        for unit in units
    )


def _semantic_detail_columns(units: list[SemanticUnit]) -> dict[str, object]:
    return {
        "使用者引用": _join_unit_field(units, "actor_ref"),
        "观点来源引用": _join_unit_field(units, "source_ref"),
        "实际体验者引用": _join_unit_field(units, "experiencer_ref"),
        "商品引用": _join_unit_field(units, "product_ref"),
        "规格引用": _join_unit_field(units, "variant_ref"),
        "事件引用": _join_unit_field(units, "event_ref"),
        "比较基准": _join_unit_field(units, "reference_basis", enum_value=True),
        "陈述类型": _join_unit_field(units, "statement_type"),
        "事实角色": _join_unit_field(units, "fact_role", enum_value=True),
        "操作": _join_unit_field(units, "operation"),
        "条件": _join_unit_field(units, "condition"),
        "部位": _join_unit_field(units, "part"),
        "因果归属": _join_unit_field(units, "causal_attribution", enum_value=True),
        "因果说明": _join_unit_field(units, "causal_attribution_reason"),
        "判定理由": _join_unit_field(units, "decision_reason"),
        "证据原文": _join_unit_field(units, "evidence"),
        "证据来源": _join_unit_field(units, "evidence_source", enum_value=True),
    }


def _outcome_detail_columns(
    result: ValidatedClassification | None,
    units: list[SemanticUnit],
    status: str,
) -> dict[str, object]:
    return {
        "未映射处置": " | ".join(
            item.disposition.value
            for item in (result.unknown_semantics if result else [])
        ),
        "评论摘要状态": result.comment_summary.status.value if result else "",
        "语义关系": _format_relations(result) if result else "",
        "Listing承诺关系": " | ".join(unit.claim_relation.value for unit in units),
        "Listing承诺编号": " | ".join(unit.claim_id or "" for unit in units),
        "处理状态": status,
        "复核原因": " | ".join(result.review_reasons if result else []),
        "模型": result.model_name if result else "",
        "提示版本": result.prompt_version if result else "",
        "分类体系版本": result.taxonomy_version if result else "",
    }


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
                **_source_detail_columns(record),
                **_classification_detail_columns(result, units, taxonomy, label_names),
                **_semantic_detail_columns(units),
                **_outcome_detail_columns(result, units, status),
            }
        )
    return rows
