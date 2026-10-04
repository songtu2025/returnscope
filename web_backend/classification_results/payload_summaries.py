from __future__ import annotations

from typing import Any

from return_semantics.schemas import TaxonomyConfig
from return_semantics.taxonomy_hierarchy import label_path, label_path_codes

CONFIRMED_STATEMENT_TYPES = {"EXPERIENCE", "EVALUATION", "REPORTED"}


def _topic_identity(
    taxonomy: TaxonomyConfig | None,
    label_code: str,
    fact: dict[str, Any],
) -> tuple[str, str, list[str], list[str]]:
    label = (
        next((value for value in taxonomy.labels if value.code == label_code), None)
        if taxonomy
        else None
    )
    if taxonomy is None or label is None:
        path = [
            str(value)
            for value in fact.get("label_path") or fact.get("full_label_path") or []
            if value
        ]
        if len(path) > 1:
            return "/".join(path[:-1]), path[-2], [], path[:-1]
        return label_code, label_code, [], []
    code_path = label_path_codes(taxonomy, label_code)
    name_path = label_path(taxonomy, label_code)
    if taxonomy.structure_version == 2 and len(code_path) > 1:
        return code_path[-2], name_path[-2], code_path[:-1], name_path[:-1]
    topic_code = label.group or label.code
    topic_name = label.group or label.name
    return topic_code, topic_name, [topic_code], [topic_name]


def _is_confirmed_fact(unit: dict[str, Any]) -> bool:
    if str(unit.get("assertion") or "AFFIRMED") != "AFFIRMED":
        return False
    statement_type = str(unit.get("statement_type") or "")
    return not statement_type or statement_type in CONFIRMED_STATEMENT_TYPES


def _scope_key(unit: dict[str, Any]) -> tuple[str, ...] | None:
    values = tuple(
        str(unit.get(field) or "").strip()
        for field in (
            "actor_ref",
            "product_ref",
            "event_ref",
            "operation",
            "part",
            "condition",
        )
    )
    return values if all(values) and "UNSPECIFIED" not in values else None


def _unit_fact_ids(unit: dict[str, Any]) -> list[str]:
    values = [
        str(value).strip() for value in unit.get("fact_ids", []) if str(value).strip()
    ]
    fact_id = str(unit.get("fact_id") or "").strip()
    if fact_id:
        values.insert(0, fact_id)
    return list(dict.fromkeys(values))


def _topic_status(
    facts: list[dict[str, Any]],
    label_codes: set[str],
    relations: list[dict[str, Any]] | None,
) -> str:
    """优先采用显式关系，否则按确定事实及其作用域归并评价。"""
    confirmed = [value for value in facts if _is_confirmed_fact(value)]
    sentiments = {
        str(value.get("sentiment") or "")
        for value in confirmed
        if value.get("sentiment")
    }
    related_types = {
        str(relation.get("relation_type") or "")
        for relation in relations or []
        if isinstance(relation, dict)
        and label_codes.intersection(
            str(value) for value in relation.get("label_codes", [])
        )
    }
    if "CONFLICT" in related_types:
        return "CONFLICT"
    if "MIXED" in related_types:
        return "MIXED"
    if not confirmed or not sentiments.intersection({"POSITIVE", "NEGATIVE"}):
        return "NO_CONFIRMED"
    if {"POSITIVE", "NEGATIVE"}.issubset(sentiments):
        positive_scopes = {
            _scope_key(value)
            for value in confirmed
            if value.get("sentiment") == "POSITIVE"
        }
        negative_scopes = {
            _scope_key(value)
            for value in confirmed
            if value.get("sentiment") == "NEGATIVE"
        }
        return (
            "CONFLICT"
            if None in positive_scopes
            or None in negative_scopes
            or positive_scopes & negative_scopes
            else "MIXED"
        )
    return "NEGATIVE" if "NEGATIVE" in sentiments else "POSITIVE"


def _topic_summaries(
    facts: list[dict[str, Any]],
    taxonomy: TaxonomyConfig | None,
    relations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    topics: dict[str, dict[str, Any]] = {}
    for fact in facts:
        label_code = str(fact.get("label_code") or "")
        topic_code, topic_name, code_path, name_path = _topic_identity(
            taxonomy, label_code, fact
        )
        topic = topics.setdefault(
            topic_code,
            {
                "topic_code": topic_code,
                "topic_name": topic_name,
                "topic_code_path": code_path,
                "topic_path": name_path,
                "facts": [],
            },
        )
        topic["facts"].append(fact)

    return [
        _summarize_topic(topics[topic_code], relations) for topic_code in sorted(topics)
    ]


def _summarize_topic(
    topic: dict[str, Any],
    relations: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """将单个已分组主题归并为状态、证据身份和计数。"""
    facts_for_topic = topic.pop("facts")
    label_codes = {
        str(value["label_code"]) for value in facts_for_topic if value.get("label_code")
    }
    status = _topic_status(facts_for_topic, label_codes, relations)
    fact_ids = [
        fact_id for value in facts_for_topic for fact_id in _unit_fact_ids(value)
    ]
    event_ids = {
        str(value["event_ref"])
        for value in facts_for_topic
        if value.get("event_ref") not in (None, "", "UNSPECIFIED")
    }
    return {
        **topic,
        "status": status,
        "supporting_fact_ids": list(dict.fromkeys(fact_ids)),
        "label_codes": sorted(label_codes),
        "fact_count": len(facts_for_topic),
        "event_count": len(event_ids),
    }


def _comment_summary_status(
    payload: dict[str, Any],
    summaries: list[dict[str, Any]],
) -> str:
    summary = payload.get("comment_summary")
    if isinstance(summary, dict):
        status = str(summary.get("status") or "")
        is_explicit = status != "NO_CONFIRMED" or any(
            summary.get(field)
            for field in ("fact_ids", "positive_label_codes", "negative_label_codes")
        )
        if is_explicit and status in {
            "POSITIVE",
            "NEGATIVE",
            "MIXED",
            "CONFLICT",
            "NO_CONFIRMED",
        }:
            return status
    statuses = {str(value["status"]) for value in summaries}
    if "CONFLICT" in statuses:
        return "CONFLICT"
    if "MIXED" in statuses or {"POSITIVE", "NEGATIVE"}.issubset(statuses):
        return "MIXED"
    if "NEGATIVE" in statuses:
        return "NEGATIVE"
    if "POSITIVE" in statuses:
        return "POSITIVE"
    return "NO_CONFIRMED"


def build_comment_summary(
    payload: dict[str, Any],
    facts: list[dict[str, Any]],
    comment_status: str,
) -> dict[str, Any]:
    """保留显式摘要，仅在缺失或为默认占位时按事实构造。"""
    current_summary = payload.get("comment_summary")
    summary_is_default = isinstance(current_summary, dict) and (
        str(current_summary.get("status") or "") == "NO_CONFIRMED"
        and not any(
            current_summary.get(field)
            for field in ("fact_ids", "positive_label_codes", "negative_label_codes")
        )
    )
    if isinstance(current_summary, dict) and not summary_is_default:
        return current_summary
    return {
        "status": comment_status,
        "fact_ids": list(
            dict.fromkeys(fact_id for fact in facts for fact_id in _unit_fact_ids(fact))
        ),
        "positive_label_codes": sorted(
            {
                str(fact["label_code"])
                for fact in facts
                if fact.get("sentiment") == "POSITIVE" and fact.get("label_code")
            }
        ),
        "negative_label_codes": sorted(
            {
                str(fact["label_code"])
                for fact in facts
                if fact.get("sentiment") == "NEGATIVE" and fact.get("label_code")
            }
        ),
    }
