"""按语义实例核对参考答案，保留重复、对象和部位差异。"""

import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, get_args

from return_semantics.schemas import ExtractedFact
from web_backend.classification_reference_scope import (
    SCOPE_FIELDS,
    SCOPE_METRICS,
    append_reference_scope,
    business_fact_pairs,
    compare_reference_scope,
)
from web_backend.reference_fact_matching import minimum_rank_matching

ERROR_METRICS = (
    "extra_labels",
    "missing_labels",
    "duplicate_units",
    "direction_errors",
    "part_errors",
    "evidence_errors",
    "model_errors",
    "statement_type_errors",
    "actor_errors",
    "product_errors",
    "plan_confirmation_errors",
    *SCOPE_METRICS,
)
HIGH_DAMAGE_METRICS = (
    "model_errors",
    "evidence_errors",
    "plan_confirmation_errors",
    "product_errors",
    "direction_errors",
    "subject_errors",
    "primary_errors",
)
WARNING_METRICS = tuple(
    metric for metric in ERROR_METRICS if metric not in HIGH_DAMAGE_METRICS
)
FACT_QUALITY_POLICY = {
    "version": "fact-reference-v4",
    "thresholds": dict.fromkeys(HIGH_DAMAGE_METRICS, 0),
    "warning_metrics": list(WARNING_METRICS),
    "min_reference_samples": 15,
    "min_reference_coverage": 80,
    "min_instance_match_rate": 80,
    "max_duplicate_rate": 10,
    "require_fact_states": False,
    "warn_incomplete_fact_states": True,
    "require_scope_dimensions": [],
    "warn_incomplete_scope_dimensions": list(SCOPE_FIELDS),
}
METRIC_LABELS = dict(
    zip(
        ERROR_METRICS,
        (
            "多标实例",
            "漏标实例",
            "重复实例",
            "方向错误",
            "明确部位漏错",
            "证据检查失败",
            "模型错误",
            "事实状态错误",
            "使用者错配",
            "商品对象错配",
            "计划或假设误确认为事实",
            *SCOPE_METRICS.values(),
        ),
        strict=True,
    )
)


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


def _signature(unit: dict) -> tuple:
    return tuple(
        unit.get(key, "")
        for key in ("label_code", "sentiment", "part", "subject", "evidence")
    )


def _duplicate_count(item: dict, side: str, expected: list[dict]) -> int:
    result = item[side]
    actual = result.get("semantic_units", [])
    facts = result.get("extracted_facts", [])
    mappings = {
        entry["fact_id"]: entry.get("label_codes", [])
        for entry in result.get("fact_mappings", [])
    }
    if not facts or not all(fact.get("event_ref") for fact in facts):
        signatures = Counter(_signature(unit) for unit in actual)
        expected_signatures = Counter(_signature(unit) for unit in expected)
        return sum(
            max(0, count - max(1, expected_signatures[signature]))
            for signature, count in signatures.items()
        )
    fact_signatures: list[tuple[Any, ...]] = []
    used = set()
    for unit in actual:
        matches = [
            fact
            for fact in facts
            if unit["label_code"] in mappings.get(fact["fact_id"], [])
            and fact.get("sentiment") == unit.get("sentiment")
            and fact.get("part") == unit.get("part")
            and all(
                span["text"] in unit.get("evidence", "")
                for span in fact.get("evidence_spans", [])
            )
        ]
        if matches:
            fact = min(
                matches, key=lambda fact: (fact["fact_id"], unit["label_code"]) in used
            )
            used.add((fact["fact_id"], unit["label_code"]))
            fact_signatures.append(
                tuple(
                    fact.get(key, "")
                    for key in (
                        "actor_ref",
                        "product_ref",
                        "event_ref",
                        "part",
                        "subject",
                        "statement_type",
                        "condition",
                    )
                )
                + (unit["label_code"], unit["sentiment"])
            )
        else:
            fact_signatures.append(_signature(unit))
    return sum(count - 1 for count in Counter(fact_signatures).values())


def _evidence_contains(outer: str, inner: str) -> bool:
    """忽略摘录边缘的终止标点；保留内部文字与否定词的逐字约束。"""
    boundary = " \t\r\n.!?。！？"
    inner = inner.strip(boundary)
    return bool(inner) and inner in outer.strip(boundary)


def _match_rank(expected: dict, actual: dict) -> tuple:
    return (
        expected.get("sentiment") != actual.get("sentiment"),
        expected.get("part", "UNSPECIFIED") not in ("UNSPECIFIED", actual.get("part")),
        bool(expected.get("evidence"))
        and not _evidence_contains(actual.get("evidence", ""), expected["evidence"]),
    )


def compare_reference(item: dict, side: str) -> dict[str, int]:
    """一对一消费实例；参考答案未指定的部位不作为错误。"""
    expected = item["reference"]["units"]
    actual = item[side].get("semantic_units", [])
    remaining = list(range(len(actual)))
    counts = dict.fromkeys(ERROR_METRICS, 0)
    counts.update(
        expected_instances=len(expected),
        actual_instances=len(actual),
        matched_instances=0,
    )
    bad_evidence = set()
    for unit in sorted(
        expected, key=lambda unit: unit.get("part", "UNSPECIFIED") == "UNSPECIFIED"
    ):
        candidates = [
            index
            for index in remaining
            if actual[index]["label_code"] == unit["label_code"]
        ]
        if not candidates:
            counts["missing_labels"] += 1
            continue
        index = min(candidates, key=lambda i: _match_rank(unit, actual[i]))
        remaining.remove(index)
        direction, part, evidence = _match_rank(unit, actual[index])
        counts["direction_errors"] += int(direction)
        counts["part_errors"] += int(part)
        counts["matched_instances"] += int(not direction and not part)
        if evidence:
            bad_evidence.add(index)
    counts["duplicate_units"] = _duplicate_count(item, side, expected)
    counts["extra_labels"] = len(remaining)
    bad_evidence.update(
        index
        for index, unit in enumerate(actual)
        if not unit.get("evidence") or unit["evidence"] not in item.get("comment", "")
    )
    counts["evidence_errors"] = len(bad_evidence)
    counts.update(compare_facts(item, side))
    counts["model_errors"] = int(item[side].get("status") == "MODEL_ERROR")
    counts["exact_label_samples"] = int(
        not any(counts[key] for key in ERROR_METRICS if key != "evidence_errors")
    )
    return counts


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


def evaluate_references(items: list[dict]) -> dict[str, Any]:
    judged = [
        item
        for item in items
        if item.get("reference") and not item["reference"]["ambiguous"]
    ]
    output: dict[str, Any] = {
        "sample_count": len(judged),
        "total_sample_count": len(items),
        "fact_state_sample_count": sum(
            bool(item["reference"].get("fact_state_complete")) for item in judged
        ),
        "scope_sample_counts": {
            dimension: sum(
                bool(item["reference"].get("scope_complete", {}).get(dimension))
                for item in judged
            )
            for dimension in SCOPE_FIELDS
        },
        "ambiguous_count": sum(
            bool(item.get("reference", {}).get("ambiguous"))
            for item in items
            if item.get("reference")
        ),
        "evidence_scope": "检查证据逐字存在且包含参考证据，允许连续扩展；未填写参考证据或观点推理是否充分仍需人工判断",
        "sides": {},
    }
    for side in ("baseline", "draft"):
        totals = Counter(
            dict.fromkeys(
                (
                    *ERROR_METRICS,
                    "exact_label_samples",
                    "expected_instances",
                    "actual_instances",
                    "matched_instances",
                ),
                0,
            )
        )
        for item in judged:
            comparison = compare_reference(item, side)
            item.setdefault("reference_comparison", {})[side] = comparison
            totals.update(comparison)
            totals["duplicate_samples"] += comparison["duplicate_units"] > 0
        output["sides"][side] = dict(totals)
    return output


def quality_gate(summary: dict, policy: dict | None = None) -> dict:
    """只用已配置的指标门槛评估，不把无参考答案当作零错误。"""
    evaluation = summary.get("reference_evaluation", {})
    if not policy:
        return {
            "status": "not_configured",
            "passed": True,
            "blocking": [],
            "warnings": [],
            "note": "未配置自动质量门槛，需人工审阅；不代表语义质量已通过",
        }
    values = evaluation.get("sides", {}).get("draft", {})
    blocking = [
        f"{METRIC_LABELS.get(metric, metric)}={values.get(metric, '未评估')}，要求不超过 {limit}"
        for metric, limit in policy["thresholds"].items()
        if metric not in values or values[metric] > limit
    ]
    warnings = [
        f"{METRIC_LABELS.get(metric, metric)}={values.get(metric, '未评估')}，请人工复核"
        for metric in policy.get("warning_metrics", [])
        if metric not in values or values[metric] > 0
    ]
    sample_count = evaluation.get("sample_count", 0)
    if sample_count < policy["min_reference_samples"]:
        blocking.append(
            f"非歧义参考样本 {sample_count} 条，至少需要 {policy['min_reference_samples']} 条"
        )
    total = evaluation.get("total_sample_count", summary.get("sample_size", 0))
    for dimension in policy.get("require_scope_dimensions", []):
        count = evaluation.get("scope_sample_counts", {}).get(dimension, 0)
        if count != total or not total:
            blocking.append(
                f"{SCOPE_FIELDS[dimension][0]}参考未完整评估：{count}/{total} 条；旧表缺列不代表零错误"
            )
    for dimension in policy.get("warn_incomplete_scope_dimensions", []):
        count = evaluation.get("scope_sample_counts", {}).get(dimension, 0)
        if count != total or not total:
            warnings.append(
                f"{SCOPE_FIELDS[dimension][0]}参考未完整评估：{count}/{total} 条；请在人工审批时核对"
            )
    coverage = sample_count / total * 100 if total else 0
    denominator = max(
        values.get("expected_instances", 0), values.get("actual_instances", 0)
    )
    match_rate = (
        values.get("matched_instances", 0) / denominator * 100
        if denominator
        else (100 if sample_count else 0)
    )
    duplicate_rate = values.get("duplicate_samples", 0) / max(1, sample_count) * 100
    for actual, limit, message, minimum in (
        (coverage, policy["min_reference_coverage"], "非歧义参考覆盖率", True),
        (match_rate, policy["min_instance_match_rate"], "实例标签匹配率", True),
        (duplicate_rate, policy["max_duplicate_rate"], "重复事实样本率", False),
    ):
        if (actual < limit) if minimum else (actual > limit):
            blocking.append(
                f"{message} {actual:.2f}%，要求{'至少' if minimum else '不超过'} {limit}%"
            )
        elif (minimum and actual < 100) or (not minimum and actual > 0):
            warnings.append(f"{message} {actual:.2f}%，请人工复核")
    if (
        policy.get("require_fact_states")
        and evaluation.get("fact_state_sample_count", 0) != total
    ):
        blocking.append(
            "事实状态参考答案不完整：每条参考行须填写事实状态及对应证据；不能将未验证状态算作通过"
        )
    if (
        policy.get("warn_incomplete_fact_states")
        and evaluation.get("fact_state_sample_count", 0) != total
    ):
        warnings.append(
            "事实状态参考答案不完整：请在人工审批时核对未标注样本的事实状态"
        )
    return {
        "status": "failed" if blocking else "passed",
        "passed": not blocking,
        "blocking": blocking,
        "warnings": warnings,
        "policy": policy,
        "reference_coverage": coverage,
        "instance_match_rate": match_rate,
        "duplicate_rate": duplicate_rate,
    }


def publication_quality_gate(
    snapshot: dict, source: dict, items: list, summary: dict
) -> dict:
    policy = source.get("quality_policy")
    if snapshot.get("taxonomy", {}).get("recognition_profile") == "fact_v2":
        policy = policy or FACT_QUALITY_POLICY
    if items:
        summary = {**summary, "reference_evaluation": evaluate_references(items)}
    return quality_gate(summary, policy)
