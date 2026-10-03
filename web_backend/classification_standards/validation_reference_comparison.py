"""按实例核对标签、方向、部位、重复和证据。"""

from collections import Counter
from typing import Any

from web_backend.classification_standards.validation_facts import (
    _evidence_contains,
    compare_facts,
)
from web_backend.classification_standards.validation_quality_policy import ERROR_METRICS


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
