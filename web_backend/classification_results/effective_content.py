"""读取完整结果并比较业务内容，执行留痕不影响结果版本。"""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any

from web_backend.common import json_text, json_value

_TRACE_FIELDS = {
    "id",
    "result_version_id",
    "source_record_id",
    "fact_id",
    "fact_ids",
    "supporting_fact_ids",
    "context_fact_ids",
    "model_name",
    "prompt_version",
    "human_review_assessment",
    "human_added_semantic_items",
    "human_semantic_reviews",
    "extracted_facts",
    "fact_mappings",
    "dimension_decisions",
    "semantic_review",
    "review_diagnostics",
    "review_reasons",
    "semantic_relations",
}


def load_content(connection: Any, version_id: str) -> dict[str, Any]:
    """复用持久化字段，避免复制源明细字段定义。"""
    units = []
    for row in connection.execute(
        "SELECT * FROM classification_units WHERE result_version_id = ? ORDER BY classification_key",
        (version_id,),
    ):
        unit = dict(row)
        unit["classification"] = json_value(unit.pop("classification_json"), {})
        unit["problem_labels"] = json_value(unit.pop("problem_labels_json"), [])
        units.append(unit)
    labels = [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM classification_unit_labels WHERE result_version_id = ?",
            (version_id,),
        )
    ]
    records = [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM classification_result_records WHERE result_version_id = ? ORDER BY source_row",
            (version_id,),
        )
    ]
    return {"units": units, "labels": labels, "records": records}


def business_hash(content: dict[str, Any]) -> str:
    """按源明细比较有效语义，分类单元拆分和技术标识不改变业务数量。"""
    units = {unit["classification_key"]: unit for unit in content["units"]}
    values = []
    for record in content["records"]:
        unit = units[record["classification_key"]]
        values.append(
            _business_value(
                {
                    "record": {
                        key: value
                        for key, value in record.items()
                        if key != "classification_key"
                    },
                    "classification": unit["classification"],
                    "processing_status": unit["processing_status"],
                    "quality_status": unit["quality_status"],
                }
            )
        )
    return hashlib.sha256(json_text(values).encode()).hexdigest()


def _business_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _business_value(item)
            for key, item in sorted(value.items())
            if key not in _TRACE_FIELDS and key != "classification_key"
        }
    if isinstance(value, list):
        return [_business_value(item) for item in value]
    return value


def retain_manual_results(prepared: dict[str, Any], previous: dict[str, Any]) -> None:
    """按源明细恢复人工结果，模型仍可处理共用原分类键的其他订单。"""
    manual = {
        unit["classification_key"]: unit
        for unit in previous["units"]
        if unit["classification"].get("human_review_assessment", {}).get("resolved")
    }
    if not manual:
        return
    records = {
        record["source_row"]: record
        for record in previous["records"]
        if record["classification_key"] in manual
    }
    for record in prepared["records"]:
        original = records.get(record["source_row"])
        if original:
            record.update(
                classification_key=original["classification_key"],
                quality_status="ready",
            )
    counts = Counter(record["classification_key"] for record in prepared["records"])
    combined = {unit["classification_key"]: unit for unit in prepared["units"]}
    combined.update(manual)
    prepared["units"] = [
        {**unit, "record_count": counts[key]}
        for key, unit in sorted(combined.items())
        if counts[key]
    ]
    prepared["labels"] = [
        label
        for label in prepared["labels"]
        if counts[label["classification_key"]]
        and label["classification_key"] not in manual
    ]
    prepared["labels"].extend(
        label for label in previous["labels"] if label["classification_key"] in manual
    )
