"""解析参考事实并核对事实状态、对象和证据对应关系。"""

import re
from difflib import SequenceMatcher
from typing import get_args

from return_semantics.schemas import ExtractedFact
from web_backend.classification_reference_scope import (
    append_reference_scope,
    business_fact_pairs,
    compare_reference_scope,
)
from web_backend.reference_fact_matching import minimum_rank_matching


def append_reference_fact(reference: dict, row: dict, identity: str, code: str) -> None:
    scope = append_reference_scope(reference, row, identity, code)
    object_refs = {}
    for column, field, pattern, allowed_refs in (
        (
            "使用者",
            "expected_actor_ref",
            r"REVIEWER|OTHER:[1-9][0-9]*",
            "空值、REVIEWER、OTHER:<正整数>",
        ),
        (
            "商品对象",
            "expected_product_ref",
            r"CURRENT|(?:CURRENT|OTHER):[1-9][0-9]*",
            "空值、CURRENT、CURRENT:<正整数>、OTHER:<正整数>",
        ),
    ):
        raw_ref = row.get(column)
        if raw_ref is None or raw_ref == "":
            raw_ref = row.get(field)
        object_ref = "" if raw_ref is None else str(raw_ref).strip()
        if object_ref and not re.fullmatch(pattern, object_ref):
            raise ValueError(
                f"参考答案 {identity} 的{column}引用无效，可用：{allowed_refs}；"
                "编号须从 1 开始，不得使用人物名称或商品描述"
            )
        object_refs[field] = object_ref
    value = str(row.get("事实状态") or row.get("expected_statement_type") or "").strip()
    reference["fact_state_complete"] = reference.get(
        "fact_state_complete", True
    ) and bool(value)
    if not value:
        return
    allowed = get_args(ExtractedFact.model_fields["statement_type"].annotation)
    if value not in allowed:
        raise ValueError(
            f"参考答案 {identity} 的事实状态无效，可用：{'、'.join(allowed)}"
        )
    evidence = str(row.get("证据") or "").strip()
    if not evidence:
        raise ValueError(f"参考答案 {identity} 的事实状态缺少证据")
    reference.setdefault("facts", []).append(
        {
            "expected_statement_type": value,
            **object_refs,
            **scope,
            "evidence": evidence,
            "label_codes": [] if code == "无标签" else [code],
        }
    )


def _evidence_contains(outer: str, inner: str) -> bool:
    """忽略摘录边缘的终止标点；保留内部文字与否定词的逐字约束。"""
    boundary = " \t\r\n.!?。！？"
    inner = inner.strip(boundary)
    return bool(inner) and inner in outer.strip(boundary)


def _fact_pairs(item: dict, side: str) -> dict[int, int]:
    """先关联事实再比较状态；证据定位不等于证据支持检查通过。"""
    facts = item[side].get("extracted_facts", [])
    mappings = {
        entry["fact_id"]: entry.get("label_codes", [])
        for entry in item[side].get("fact_mappings", [])
    }
    edges = []
    for reference_index, expected in enumerate(item["reference"].get("facts", [])):
        for actual_index, fact in enumerate(facts):
            spans = [
                text
                for span in fact.get("evidence_spans", [])
                for text in (span["text"], *span["text"].splitlines())
                if text.strip()
            ]
            matching_spans = [
                span
                for span in spans
                if span in item.get("comment", "")
                and (
                    _evidence_contains(span, expected["evidence"])
                    or _evidence_contains(expected["evidence"], span)
                )
            ]
            if not matching_spans:
                continue
            evidence_rank = min(
                (
                    span.strip(" \t\r\n.!?。！？")
                    != expected["evidence"].strip(" \t\r\n.!?。！？"),
                    abs(len(span) - len(expected["evidence"])),
                )
                for span in matching_spans
            )
            actual_codes = mappings.get(fact["fact_id"], [])
            rank = (
                not any(code in actual_codes for code in expected["label_codes"])
                if expected.get("label_codes")
                else False,
                bool(expected.get("expected_actor_ref"))
                and expected["expected_actor_ref"] != fact.get("actor_ref"),
                bool(expected.get("expected_product_ref"))
                and expected["expected_product_ref"] != fact.get("product_ref"),
                *evidence_rank,
                # 多个事实共用整段证据时，以观点原文锚点进一步定位，不用状态决定身份。
                1000
                - round(
                    1000
                    * SequenceMatcher(
                        None,
                        expected["evidence"].casefold(),
                        fact.get("opinion", "").casefold(),
                    ).ratio()
                )
                if fact.get("opinion")
                else 1000,
                expected["expected_statement_type"] != fact.get("statement_type"),
            )
            edges.append((rank, reference_index, actual_index))
    return minimum_rank_matching(
        len(item["reference"].get("facts", [])), len(facts), edges
    )


def _fact_is_confirmed(result: dict, fact: dict) -> bool:
    codes = [
        code
        for mapping in result.get("fact_mappings", [])
        if mapping["fact_id"] == fact["fact_id"]
        for code in mapping.get("label_codes", [])
    ]
    return any(
        unit["label_code"] in codes
        and unit.get("part") == fact.get("part")
        and unit.get("sentiment") == fact.get("sentiment")
        and (not fact.get("opinion") or fact["opinion"] in unit.get("opinion", ""))
        and all(
            _evidence_contains(unit.get("evidence", ""), span["text"])
            for span in fact.get("evidence_spans", [])
        )
        for unit in result.get("semantic_units", [])
    )


def compare_facts(item: dict, side: str) -> dict[str, int]:
    counts = dict.fromkeys(
        (
            "statement_type_errors",
            "actor_errors",
            "product_errors",
            "plan_confirmation_errors",
        ),
        0,
    )
    facts = item[side].get("extracted_facts", [])
    pairs = _fact_pairs(item, side)
    projected_pairs = business_fact_pairs(item, side, pairs)
    counts.update(compare_reference_scope(item, side, pairs))
    for reference_index, expected in enumerate(item["reference"].get("facts", [])):
        if reference_index not in pairs:
            continue
        actual = facts[pairs[reference_index]]
        if reference_index in projected_pairs:
            expected_state = expected["expected_statement_type"]
            actual_state = actual.get("statement_type")
            confirmed_states = {"EXPERIENCE", "EVALUATION"}
            counts["statement_type_errors"] += expected_state != actual_state and not (
                expected_state in confirmed_states and actual_state in confirmed_states
            )
        for field, metric in (
            ("actor_ref", "actor_errors"),
            ("product_ref", "product_errors"),
        ):
            counts[metric] += bool(expected.get(f"expected_{field}")) and expected[
                f"expected_{field}"
            ] != actual.get(field)
        if expected["expected_statement_type"] in {
            "INTENT",
            "PREDICTION",
            "HYPOTHESIS",
            "NEGATED",
            "NOT_TESTED",
            "ADVICE",
        } and not expected.get("label_codes"):
            counts["plan_confirmation_errors"] += _fact_is_confirmed(item[side], actual)
    return counts
