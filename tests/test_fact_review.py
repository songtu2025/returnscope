import json

import pytest

from return_semantics import prompt
from return_semantics.review import (
    classifications_match,
    reconcile_secondary,
    should_run_secondary,
)
from return_semantics.schemas import (
    DimensionDecision,
    ExtractedFact,
    FactMapping,
    SemanticUnit,
    UnknownSemantic,
    ValidatedClassification,
)


def result_with_fact(**updates):
    fact = ExtractedFact.model_validate(
        {
            "fact_id": "a",
            "actor_ref": "REVIEWER",
            "product_ref": "CURRENT",
            "event_ref": "event",
            "subject": "PRODUCT",
            "statement_type": "EXPERIENCE",
            "opinion": "实际评价",
            "sentiment": "POSITIVE",
            "part": "UNSPECIFIED",
            "condition": "",
            "evidence_spans": [{"text": "This worked well."}],
            **updates,
        }
    )
    return ValidatedClassification.model_validate(
        {
            "classification_key": "test",
            "semantic_units": [],
            "unknown_semantics": [],
            "problem_label_codes": [],
            "positive_label_codes": [],
            "primary_label_codes": [],
            "status": "SECONDARY_REVIEW",
            "review_reasons": [],
            "model_name": "fake",
            "prompt_version": "fact-test",
            "taxonomy_version": "test",
            "extracted_facts": [fact.model_dump(mode="json")],
            "fact_mappings": [{"fact_id": fact.fact_id, "label_codes": []}],
        }
    )


def result_with_dimension(
    *,
    fact_id="F1",
    event_ref="E1",
    evidence="Touch controls require repeated presses.",
    label_code="TOUCH_NEGATIVE",
    experiencer_ref="REVIEWER",
    product_ref="CURRENT",
    variant_ref="M",
    condition="outdoors",
):
    result = result_with_fact(
        fact_id=fact_id,
        event_ref=event_ref,
        source_ref="REVIEWER",
        experiencer_ref=experiencer_ref,
        product_ref=product_ref,
        variant_ref=variant_ref,
        opinion="触屏操作困难",
        sentiment="NEGATIVE",
        condition=condition,
        evidence_spans=[{"text": evidence}],
    )
    result.fact_mappings = [FactMapping(fact_id=fact_id, label_codes=[label_code])]
    result.semantic_units = [
        SemanticUnit.model_validate(
            {
                "subject": "PRODUCT",
                "label_code": label_code,
                "opinion": "触屏操作困难",
                "sentiment": "NEGATIVE",
                "assertion": "AFFIRMED",
                "part": "UNSPECIFIED",
                "evidence": evidence,
                "implicit": False,
                "fact_id": fact_id,
                "fact_ids": [fact_id],
                "actor_ref": "REVIEWER",
                "source_ref": "REVIEWER",
                "experiencer_ref": experiencer_ref,
                "product_ref": product_ref,
                "variant_ref": variant_ref,
                "event_ref": event_ref,
                "condition": condition,
            }
        )
    ]
    result.dimension_decisions = [
        DimensionDecision.model_validate(
            {
                "parent_code": "TOUCHSCREEN",
                "scope": {
                    "source_ref": "REVIEWER",
                    "experiencer_ref": experiencer_ref,
                    "product_ref": product_ref,
                    "variant_ref": variant_ref,
                    "event_ref": event_ref,
                    "condition": condition,
                },
                "verdict_label_code": label_code,
                "supporting_fact_ids": [fact_id],
                "context_fact_ids": [],
                "reason": "形成最终维度结论",
            }
        )
    ]
    result.problem_label_codes = [label_code]
    result.primary_label_codes = [label_code]
    return ValidatedClassification.model_validate(result.model_dump(mode="json"))


@pytest.mark.parametrize(
    "change",
    [
        {"actor_ref": "OTHER:1"},
        {"product_ref": "CURRENT:1"},
        {"statement_type": "PREDICTION"},
        {"condition": "仅首次"},
    ],
)
def test_same_labels_do_not_hide_fact_disagreement(change):
    first = result_with_fact()
    second = result_with_fact(**change)
    assert not classifications_match(first, second)
    assert reconcile_secondary(first, second).status == "MANUAL_REVIEW"


def test_primary_marker_difference_does_not_trigger_review():
    first = result_with_fact()
    second = result_with_fact(is_primary_reason=True)

    assert classifications_match(first, second)
    assert reconcile_secondary(first, second).status == "AUTO_APPROVED"


def test_manual_rule_preserves_model_difference_diagnostic():
    first = result_with_fact()
    first.review_reasons = ["语义边界需人工确认"]
    second = result_with_fact(condition="仅首次")

    result = reconcile_secondary(first, second)

    assert result.status == "MANUAL_REVIEW"
    assert "两次模型的语义结果不一致" in result.review_reasons
    assert result.review_diagnostics[0].code == "MODEL_RESULT_MISMATCH"
    assert "条件=仅首次" in result.review_diagnostics[0].secondary_result


def test_model_generated_identifiers_do_not_create_false_disagreement():
    assert classifications_match(
        result_with_fact(), result_with_fact(fact_id="another", event_ref="renamed")
    )


def test_event_partition_difference_requires_review():
    first = result_with_fact()
    another = first.extracted_facts[0].model_copy(update={"fact_id": "b"})
    first.extracted_facts.append(another)
    first.fact_mappings.append(FactMapping(fact_id="b"))
    second = first.model_copy(deep=True)
    second.extracted_facts[1].event_ref = "different_event"
    assert not classifications_match(first, second)


def test_dimension_review_ignores_generated_ids_and_context_wording():
    first = result_with_dimension()
    context = first.extracted_facts[0].model_copy(
        update={
            "fact_id": "F2",
            "fact_role": "CONTEXT",
            "opinion": "基础触屏能够响应",
            "evidence_spans": [{"text": "A swipe can register."}],
        }
    )
    first.extracted_facts.append(context)
    first.fact_mappings.append(FactMapping(fact_id="F2", disposition="EVIDENCE_ONLY"))
    first.dimension_decisions[0].context_fact_ids = ["F2"]

    second = result_with_dimension(
        fact_id="support-renamed",
        event_ref="event-renamed",
        evidence="Touch controls require repeated presses",
    )
    other_context = context.model_copy(
        update={
            "fact_id": "context-renamed",
            "event_ref": "event-renamed",
            "opinion": "可以完成一次滑动",
            "evidence_spans": [{"text": "One swipe worked."}],
        }
    )
    second.extracted_facts.append(other_context)
    second.fact_mappings.append(
        FactMapping(fact_id="context-renamed", disposition="EVIDENCE_ONLY")
    )
    second.dimension_decisions[0].context_fact_ids = ["context-renamed"]

    assert classifications_match(first, second)
    assert reconcile_secondary(first, second).status == "AUTO_APPROVED"


def test_normal_abstention_difference_does_not_trigger_review():
    first = result_with_dimension()
    second = first.model_copy(deep=True)
    abstention = first.extracted_facts[0].model_copy(
        update={
            "fact_id": "F2",
            "event_ref": "E2",
            "statement_type": "PREDICTION",
            "opinion": "未来可能更灵敏",
            "evidence_spans": [{"text": "It may improve later."}],
        }
    )
    second.extracted_facts.append(abstention)
    second.fact_mappings.append(
        FactMapping(fact_id="F2", disposition="EXPECTED_ABSTENTION")
    )
    second.unknown_semantics.append(
        UnknownSemantic.model_validate(
            {
                "opinion": abstention.opinion,
                "evidence": "It may improve later.",
                "reason": "预测不形成已确认标签",
                "disposition": "EXPECTED_ABSTENTION",
                "fact_id": "F2",
                "event_ref": "E2",
                "statement_type": "PREDICTION",
            }
        )
    )

    assert classifications_match(first, second)


@pytest.mark.parametrize(
    "change",
    [
        {"experiencer_ref": "OTHER:1"},
        {"product_ref": "OTHER:1"},
        {"variant_ref": "L"},
        {"condition": "indoors"},
        {"label_code": "TOUCH_POSITIVE"},
    ],
)
def test_dimension_review_preserves_business_scope_and_verdict(change):
    assert not classifications_match(
        result_with_dimension(),
        result_with_dimension(**change),
    )


def test_dimension_review_preserves_substantively_different_evidence():
    assert not classifications_match(
        result_with_dimension(evidence="Touch controls require repeated presses."),
        result_with_dimension(evidence="The lining feels warm."),
    )


@pytest.mark.parametrize(
    "reason",
    [
        "待确认事实 a: PREDICTION",
        "fact_v2尚未完成Listing承诺关系核验，需人工确认；未推断承诺关系",
    ],
)
def test_model_agreement_cannot_remove_unresolved_fact_review(reason):
    first = result_with_fact()
    first.review_reasons = [reason]
    second = first.model_copy(deep=True)
    assert not should_run_secondary(first)
    result = reconcile_secondary(first, second)
    assert result.status == "MANUAL_REVIEW"
    assert reason in result.review_reasons


def test_legacy_without_fact_trace_keeps_existing_agreement_behavior():
    first = result_with_fact()
    first.extracted_facts = []
    first.fact_mappings = []
    assert reconcile_secondary(first, first).status == "AUTO_APPROVED"


@pytest.mark.parametrize(
    "profile,version",
    [
        ("legacy_v3", "evidence-validator-v1"),
        ("semantic_v1", "evidence-validator-v2"),
        ("fact_v2", "evidence-fact-validator-v11"),
    ],
)
def test_review_contract_version_isolated_to_fact_profile(
    taxonomy, monkeypatch, profile, version
):
    candidate = taxonomy.model_copy(update={"recognition_profile": profile})
    captured = []
    sha256 = prompt.hashlib.sha256

    def capture(payload):
        captured.append(json.loads(payload))
        return sha256(payload)

    monkeypatch.setattr(prompt.hashlib, "sha256", capture)
    prompt.recognition_fingerprint(candidate)
    assert captured[0]["validator_version"] == version
