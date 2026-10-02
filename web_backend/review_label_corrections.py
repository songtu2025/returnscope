from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from return_semantics.semantic_review import build_semantic_review_view
from web_backend.review_batch_editing import ReviewBatchEditingMixin


def _corrected_units(
    unit: dict[str, Any], reviews: dict[str, str]
) -> list[dict[str, Any]]:
    fact_ids = list(dict.fromkeys(unit.get("fact_ids", [])))
    if not fact_ids and unit.get("fact_id"):
        fact_ids = [unit["fact_id"]]
    if not fact_ids:
        items = cast(
            list[dict[str, Any]],
            build_semantic_review_view({"semantic_units": [unit]}, "")[
                "semantic_items"
            ],
        )
        item = items[0]
        return [
            {**unit, "label_code": reviews.get(item["item_id"], unit["label_code"])}
        ]

    labels: dict[str, list[str]] = {}
    for fact_id in fact_ids:
        code = reviews.get(f"fact:{fact_id}", unit["label_code"])
        labels.setdefault(code, []).append(fact_id)
    if len(labels) == 1:
        return [{**unit, "label_code": next(iter(labels))}]
    # 合并语义项中的事实被分别更正时，保留其他事实原有的标签。
    return [
        {**unit, "label_code": code, "fact_id": ids[0], "fact_ids": ids}
        for code, ids in labels.items()
    ]


def apply_semantic_label_corrections(
    classification: dict[str, Any],
) -> dict[str, Any]:
    """发布时将逐项标签更正投影到统计数据，保留复核草稿和原版本。"""
    reviews = {
        item["semantic_item_id"]: item["label_code"]
        for item in classification.get("human_semantic_reviews", [])
        if item["action"] == "change_label"
    }
    if not reviews:
        return classification
    result = deepcopy(classification)
    original_units = result.get("semantic_units", [])
    units: list[dict[str, Any]] = []
    problem_codes: list[str] = []
    primary_codes: list[str] = []
    for unit in original_units:
        corrected = _corrected_units(unit, reviews)
        units.extend(corrected)
        codes = [item["label_code"] for item in corrected]
        if unit["label_code"] in result.get("problem_label_codes", []):
            problem_codes.extend(codes)
        if unit["label_code"] in result.get("primary_label_codes", []):
            primary_codes.extend(codes)
    result["semantic_units"] = units
    for mapping in result.get("fact_mappings", []):
        selected = reviews.get(f"fact:{mapping['fact_id']}")
        if selected and any(
            mapping["fact_id"] == unit.get("fact_id")
            or mapping["fact_id"] in unit.get("fact_ids", [])
            for unit in units
        ):
            mapping.update(
                label_codes=[selected], candidate_label_codes=[], disposition=None
            )
    problems, positives, negatives = ReviewBatchEditingMixin._project_review_labels(
        units, problem_codes, "", ""
    )
    result["problem_label_codes"] = problems
    result["positive_label_codes"] = positives
    result["primary_label_codes"] = list(dict.fromkeys(primary_codes))
    summary = dict(result.get("comment_summary", {}))
    summary.update(positive_label_codes=positives, negative_label_codes=negatives)
    result["comment_summary"] = summary
    return result
