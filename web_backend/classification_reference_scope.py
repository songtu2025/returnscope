"""参考事实的事件关系、条件、责任主体及主因契约。"""

import re
from itertools import combinations

from return_semantics.schemas import SubjectCode

SCOPE_METRICS = {
    "event_errors": "事件关系错误",
    "condition_errors": "条件遗漏",
    "subject_errors": "责任主体错误",
    "primary_errors": "主因错误",
}
SCOPE_FIELDS = {
    "event": ("事件", "expected_event_ref"),
    "condition": ("条件", "expected_condition"),
    "subject": ("责任主体", "expected_subject"),
    "primary": ("是否主因", "expected_primary"),
}


def append_reference_scope(
    reference: dict, row: dict, identity: str, code: str
) -> dict:
    fields = {}
    complete = reference.setdefault("scope_complete", {})
    for dimension, (column, field) in SCOPE_FIELDS.items():
        value = str(row.get(column) or row.get(field) or "").strip()
        complete[dimension] = complete.get(dimension, True) and bool(value)
        if value:
            fields[field] = value
    subject = fields.get("expected_subject")
    if subject and subject not in {item.value for item in SubjectCode}:
        raise ValueError(f"参考答案 {identity} 的责任主体无效")
    primary = fields.get("expected_primary")
    if primary and primary not in {"是", "否"}:
        raise ValueError(f"参考答案 {identity} 的是否主因须为是或否")
    if primary == "是":
        if code == "无标签":
            raise ValueError(f"参考答案 {identity} 的无标签事实不能作为主因")
        reference.setdefault("primary_label_codes", []).append(code)
    if "expected_condition" in fields:
        value = fields["expected_condition"]
        fields["expected_condition"] = (
            []
            if value == "无"
            else [part.strip() for part in value.split("||") if part.strip()]
        )
        if value != "无" and not fields["expected_condition"]:
            raise ValueError(f"参考答案 {identity} 的条件须填写短语或无")
    return fields


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def business_fact_pairs(item: dict, side: str, pairs: dict[int, int]) -> dict[int, int]:
    """发布范围只投影至少一侧关联业务标签的已配对事实。"""
    labeled_ids = {
        mapping.get("fact_id")
        for mapping in item[side].get("fact_mappings", [])
        if mapping.get("label_codes")
    }
    expected = item["reference"].get("facts", [])
    actual = item[side].get("extracted_facts", [])
    return {
        left: right
        for left, right in pairs.items()
        if expected[left].get("label_codes")
        or actual[right].get("fact_id") in labeled_ids
    }


def compare_reference_scope(item: dict, side: str, pairs: dict[int, int]) -> dict:
    pairs = business_fact_pairs(item, side, pairs)
    reference = item["reference"]
    expected = reference.get("facts", [])
    actual = item[side].get("extracted_facts", [])
    counts = dict.fromkeys(SCOPE_METRICS, 0)
    event_errors = set()
    for index, fact in enumerate(expected):
        if index not in pairs:
            continue
        match = actual[pairs[index]]
        if fact.get("expected_subject"):
            counts["subject_errors"] += fact["expected_subject"] != match.get("subject")
        if "expected_condition" in fact:
            retained_text = [
                _normalize(match.get(field, "")) for field in ("condition", "opinion")
            ] + [
                _normalize(span.get("text", ""))
                for span in match.get("evidence_spans", [])
            ]
            phrases = fact["expected_condition"]
            # 条件列记录必须保留的短语；“无”不限制保留其他原文条件。
            counts["condition_errors"] += any(
                not any(_normalize(phrase) in text for text in retained_text)
                for phrase in phrases
            )
        if fact.get("expected_event_ref") and not match.get("event_ref"):
            event_errors.add(index)
    # 事件编号由各自文本独立命名，只检查配对事实之间的同事件关系。
    event_indices = [
        index for index in pairs if expected[index].get("expected_event_ref")
    ]
    for left, right in combinations(event_indices, 2):
        expected_same = (
            expected[left]["expected_event_ref"]
            == expected[right]["expected_event_ref"]
        )
        actual_same = actual[pairs[left]].get("event_ref") == actual[pairs[right]].get(
            "event_ref"
        )
        if expected_same != actual_same:
            event_errors.update((left, right))
    counts["event_errors"] = len(event_errors)
    if reference.get("scope_complete", {}).get("primary"):
        primary_fact_ids = {
            fact.get("fact_id") for fact in actual if fact.get("is_primary_reason")
        }
        mapped_primary = {
            code
            for mapping in item[side].get("fact_mappings", [])
            if mapping.get("fact_id") in primary_fact_ids
            for code in mapping.get("label_codes", [])
        }
        expected_primary = set(reference.get("primary_label_codes", []))
        counts["primary_errors"] = int(
            expected_primary != set(item[side].get("primary_label_codes", []))
            or expected_primary != mapped_primary
        )
    return counts
