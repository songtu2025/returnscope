import pytest

from return_semantics.fact_pipeline import _retain_fact_unit, extraction_messages
from return_semantics.schemas import SemanticUnit


@pytest.mark.parametrize(
    "change,evidence,expected",
    [
        ({}, "Support replied clearly and replaced it the same day.", 1),
        ({}, "replaced it the same day.", 2),
        ({"condition": "next month"}, "replaced it the same day.", 2),
        ({"event": "second"}, "replaced it the same day.", 2),
        ({"actor": "OTHER:1"}, "replaced it the same day.", 2),
        ({"product": "CURRENT:2"}, "replaced it the same day.", 2),
        ({"subject": "PRODUCT"}, "replaced it the same day.", 2),
        ({"part": "FINGER"}, "replaced it the same day.", 2),
        ({}, "A later reply was helpful.", 2),
        ({"condition": ""}, "Support replied clearly and replaced it the same day.", 2),
        (
            {"statement_type": "EVALUATION"},
            "Support replied clearly and replaced it the same day.",
            2,
        ),
        (
            {"condition": "not same day"},
            "Support replied clearly and replaced it the same day.",
            2,
        ),
    ],
)
def test_condition_containment_merges_only_same_event_overlapping_evidence(
    change, evidence, expected
):
    first_evidence = "Support replied clearly and replaced it the same day."
    comment = first_evidence + " A later reply was helpful."
    values = {
        "actor": "REVIEWER",
        "product": "CURRENT:1",
        "event": "first",
        "subject": "SERVICE",
        "part": "UNSPECIFIED",
        "code": "SERVICE_GOOD",
        "sentiment": "POSITIVE",
        "statement_type": "EXPERIENCE",
        "condition": "same day",
    }
    first = SemanticUnit(
        label_code="SERVICE_GOOD",
        opinion="clear reply",
        sentiment="POSITIVE",
        subject="SERVICE",
        evidence=first_evidence,
        part="UNSPECIFIED",
        assertion="AFFIRMED",
        implicit=False,
    )
    units, seen = [], {}
    _retain_fact_unit(units, seen, tuple(values.values()), first, comment)
    values.update({"condition": "same day; replacement arranged", **change})
    second = first.model_copy(
        update={
            "opinion": "replacement arranged",
            "evidence": evidence,
            "subject": values["subject"],
            "part": values["part"],
        }
    )
    _retain_fact_unit(units, seen, tuple(values.values()), second, comment)
    assert len(units) == expected
    if expected == 1:
        assert units[0].opinion == "clear reply；replacement arranged"
        assert units[0].evidence == first_evidence


def test_advice_and_denied_recommendation_require_separate_events(taxonomy):
    instruction = extraction_messages("review", taxonomy)[0]["content"]
    assert "使用操作建议ADVICE与否认购买推荐NEGATED是独立动作时应分事件" in instruction
    assert "不因出现在同一句或同一段就合并事件" in instruction


def test_after_is_not_contained_in_not_after():
    from return_semantics.fact_pipeline import _overlapping_fact_identity

    unit = SemanticUnit(
        label_code="SERVICE_GOOD",
        opinion="reply",
        sentiment="POSITIVE",
        subject="SERVICE",
        evidence="The reply was helpful.",
        part="UNSPECIFIED",
        assertion="AFFIRMED",
        implicit=False,
    )
    assert not _overlapping_fact_identity(
        ("event", "after"), ("event", "not after"), unit, unit
    )
    assert not _overlapping_fact_identity(("event", ""), ("event", "after"), unit, unit)
    assert not _overlapping_fact_identity(
        ("event", "after"), ("event", "after"), unit, unit
    )
