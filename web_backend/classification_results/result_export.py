"""构造结果和语义工作表的导出行，保持已有列顺序及空值规则。"""

from __future__ import annotations

import json
from typing import Any


def semantic_export_rows(
    item: dict[str, Any], version: dict[str, Any]
) -> list[dict[str, Any]]:
    return [_semantic_export_row(item, unit, version) for unit in item["atomic_facts"]]


def _semantic_export_row(
    item: dict[str, Any], unit: dict[str, Any], version: dict[str, Any]
) -> dict[str, Any]:
    path = unit.get("label_path", [])
    return {
        "source_record_id": item["source_record_id"],
        "source_row": item["source_row"],
        "label_code": unit["label_code"],
        "完整路径": " → ".join(path),
        "中文事实": unit.get("fact_text_zh") or "",
        "原文证据": unit.get("original_evidence") or "",
        "事实编号": unit.get("fact_id") or "",
        "使用者": unit.get("actor_ref") or "",
        "商品": unit.get("product_ref") or "",
        "事件": unit.get("event_ref") or "",
        "陈述类型": unit.get("statement_type") or "",
        "操作": unit.get("operation") or "",
        "条件": unit.get("condition") or "",
        "确定性": unit.get("certainty") or "AFFIRMED",
        "因果归属": unit.get("causal_attribution") or "UNKNOWN",
        "因果说明": unit.get("causal_attribution_reason") or "",
        "判定理由": unit.get("decision_reason") or "",
        "证据来源": unit.get("evidence_source") or "UNKNOWN",
        **{f"第{index}级标签": name for index, name in enumerate(path, 1)},
        "证据原文": unit.get("evidence", ""),
        "标准版本": version.get("standard_version_id", ""),
    }


def classification_export_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_record_id": item["source_record_id"],
        "source_row": item["source_row"],
        "return_date": item["return_date"],
        "order_id": item["order_id"],
        "store_site": item["store_site"],
        "listing": item["listing"],
        "product_name": item["product_name"],
        "source_sku": item["source_sku"],
        "matched_msku": item["matched_msku"],
        "product_sku": item["product_sku"],
        "asin": item["asin"],
        "category_a": item["category_a"],
        "category_b": item["category_b"],
        "reason": item["reason"],
        "comment": item["comment"],
        "product_match_status": item["product_match_status"],
        "quality_status": item["quality_status"],
        "processing_status": item["processing_status"],
        "semantic_disposition": item["semantic_disposition"],
        "problem_labels": " | ".join(item["problem_labels"]),
        "classification_json": json.dumps(
            item["classification"],
            ensure_ascii=False,
        ),
    }
