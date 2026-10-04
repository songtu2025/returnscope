from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from test_taxonomy_hierarchy import tree_payload as tree_payload

from return_semantics.schemas import TaxonomyConfig
from web_backend import classification_result_payload as payloads
from web_backend import classification_result_service as services
from web_backend.classification_results import payload_summaries as summaries


def _scoped_fact(direction: str, **values: Any) -> dict[str, Any]:
    return {
        "label_code": "A",
        "fact_id": "F1",
        "sentiment": direction,
        "actor_ref": "REVIEWER",
        "product_ref": "CURRENT",
        "event_ref": "E1",
        "operation": "试穿",
        "part": "WHOLE",
        "condition": "合成场景",
        **values,
    }


@pytest.mark.parametrize(
    ("positive_values", "negative_values", "expected"),
    [
        ({}, {}, "CONFLICT"),
        ({}, {"event_ref": "E2"}, "MIXED"),
        ({}, {"actor_ref": "OTHER"}, "MIXED"),
        ({}, {"condition": ""}, "CONFLICT"),
        ({}, {"assertion": "DENIED"}, "POSITIVE"),
        ({"assertion": "DENIED"}, {}, "NEGATIVE"),
        ({"assertion": "DENIED"}, {"statement_type": "PREDICTION"}, "NO_CONFIRMED"),
        ({"sentiment": "NEUTRAL"}, {"sentiment": "NEUTRAL"}, "NO_CONFIRMED"),
    ],
)
def test_topic_status_preserves_scope_and_confirmed_fact_rules(
    positive_values: dict[str, Any],
    negative_values: dict[str, Any],
    expected: str,
) -> None:
    facts = [
        _scoped_fact("POSITIVE", **positive_values),
        _scoped_fact("NEGATIVE", **negative_values),
    ]
    before = deepcopy(facts)
    assert summaries._topic_summaries(facts, None)[0]["status"] == expected
    assert facts == before


@pytest.mark.parametrize(
    ("relations", "expected"),
    [
        ([{"relation_type": "MIXED", "label_codes": ["A"]}], "MIXED"),
        ([{"relation_type": "CONFLICT", "label_codes": ["A"]}], "CONFLICT"),
        (
            [
                {"relation_type": "MIXED", "label_codes": ["A"]},
                {"relation_type": "CONFLICT", "label_codes": ["A"]},
            ],
            "CONFLICT",
        ),
        ([{"relation_type": "MIXED", "label_codes": ["OTHER"]}], "NO_CONFIRMED"),
    ],
)
def test_explicit_relations_take_priority_only_for_matching_labels(
    relations: list[dict[str, Any]], expected: str
) -> None:
    facts = [_scoped_fact("POSITIVE", assertion="DENIED")]
    assert summaries._topic_summaries(facts, None, relations)[0]["status"] == expected


def test_topic_summary_keeps_sorting_fact_identity_order_and_event_counts() -> None:
    facts = [
        _scoped_fact("NEGATIVE", label_code="Z", fact_id="F3"),
        _scoped_fact("POSITIVE", fact_id=" F2 ", fact_ids=[" F1 ", "F2", ""]),
        _scoped_fact("NEGATIVE", fact_id="F1", event_ref="UNSPECIFIED"),
        _scoped_fact("NEGATIVE", fact_id="F4", event_ref="E2"),
    ]
    before = deepcopy(facts)
    topics = summaries._topic_summaries(facts, None)
    assert [topic["topic_code"] for topic in topics] == ["A", "Z"]
    assert topics[0]["supporting_fact_ids"] == ["F2", "F1", "F4"]
    assert topics[0]["label_codes"] == ["A"]
    assert topics[0]["fact_count"] == 3
    assert topics[0]["event_count"] == 2
    assert facts == before


def test_topic_identity_uses_tree_parent_and_preserves_legacy_fallback(
    tree_payload: dict[str, Any], taxonomy: TaxonomyConfig
) -> None:
    tree = TaxonomyConfig.model_validate(tree_payload)
    assert summaries._topic_identity(tree, "COLD", {}) == (
        "WARMTH",
        "保暖性",
        ["FUNCTION", "WARMTH"],
        ["功能", "保暖性"],
    )
    label = taxonomy.labels[0]
    assert summaries._topic_identity(taxonomy, label.code, {}) == (
        label.group,
        label.group,
        [label.group],
        [label.group],
    )
    legacy = {"full_label_path": ["功能", "保暖性", "不保暖"]}
    assert summaries._topic_identity(tree, "MISSING", legacy) == (
        "功能/保暖性",
        "保暖性",
        [],
        ["功能", "保暖性"],
    )
    assert summaries._topic_identity(None, "A", {}) == ("A", "A", [], [])


@pytest.mark.parametrize(
    ("summary", "expected", "preserved"),
    [
        (None, "NEGATIVE", False),
        ({"status": "NO_CONFIRMED"}, "NEGATIVE", False),
        ({"status": "NO_CONFIRMED", "fact_ids": ["F1"]}, "NO_CONFIRMED", True),
        ({"status": "POSITIVE"}, "POSITIVE", True),
        ({"status": "INVALID"}, "NEGATIVE", True),
    ],
)
def test_comment_summary_keeps_explicit_values_and_replaces_default_placeholder(
    summary: dict[str, Any] | None, expected: str, preserved: bool
) -> None:
    facts = [_scoped_fact("NEGATIVE")]
    payload = {} if summary is None else {"comment_summary": summary}
    before = deepcopy(payload)
    topics = summaries._topic_summaries(facts, None)
    status = summaries._comment_summary_status(payload, topics)
    built = summaries.build_comment_summary(payload, facts, status)
    assert status == expected
    assert (built is summary) is preserved
    if not preserved:
        assert built == {
            "status": "NEGATIVE",
            "fact_ids": ["F1"],
            "positive_label_codes": [],
            "negative_label_codes": ["A"],
        }
    assert payload == before


def test_generated_comment_summary_keeps_fact_order_and_sorted_label_sets() -> None:
    facts = [
        _scoped_fact("POSITIVE", label_code="Z", fact_id="F2", fact_ids=["F1"]),
        _scoped_fact("NEGATIVE", label_code="B", fact_id="F1"),
        _scoped_fact("POSITIVE", label_code="A", fact_id="F3"),
    ]
    assert summaries.build_comment_summary({}, facts, "MIXED") == {
        "status": "MIXED",
        "fact_ids": ["F2", "F1", "F3"],
        "positive_label_codes": ["A", "Z"],
        "negative_label_codes": ["B"],
    }


def test_payload_and_service_entry_points_share_summary_implementation() -> None:
    for name in (
        "CONFIRMED_STATEMENT_TYPES",
        "_comment_summary_status",
        "_is_confirmed_fact",
        "_scope_key",
        "_topic_identity",
        "_topic_summaries",
        "_unit_fact_ids",
    ):
        assert getattr(payloads, name) is getattr(summaries, name)
        assert getattr(services, name) is getattr(summaries, name)
