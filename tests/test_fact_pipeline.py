import json
from types import SimpleNamespace

import pytest

from return_semantics import prompt
from return_semantics.fact_pipeline import (
    EvidenceLabelAdjudication,
    EvidenceLabelAdjudications,
    FactMappings,
    classify_facts,
    compile_evidence_label_adjudications,
    compile_fact_classification,
    merge_coverage_facts,
)
from return_semantics.model_client import JsonlCache, JsonModelCallResult
from return_semantics.pipeline import _call_with_cache
from return_semantics.schemas import (
    ExtractedFact,
    FactMapping,
    ListingClaimsConfig,
    ModelClassification,
    TaxonomyConfig,
)


@pytest.fixture
def fact_taxonomy():
    return TaxonomyConfig.model_validate(
        {
            "version": "test",
            "recognition_profile": "fact_v2",
            "agent_family": "测试",
            "product_context": "测试商品",
            "labels": [
                {
                    "code": "WARM",
                    "name": "保暖",
                    "group": "功能",
                    "allowed_sentiments": ["POSITIVE"],
                },
                {
                    "code": "COLD",
                    "name": "不保暖",
                    "group": "功能",
                    "allowed_sentiments": ["NEGATIVE"],
                },
                {
                    "code": "FIT",
                    "name": "合身",
                    "group": "尺码",
                    "allowed_sentiments": ["POSITIVE"],
                },
            ],
        }
    )


def make_fact(identifier="a", **updates):
    return ExtractedFact.model_validate(
        {
            "fact_id": identifier,
            "actor_ref": "REVIEWER",
            "product_ref": "CURRENT",
            "event_ref": "首次使用",
            "statement_type": "EXPERIENCE",
            "opinion": "手套暖和",
            "sentiment": "POSITIVE",
            "part": "UNSPECIFIED",
            "condition": "",
            "evidence_spans": [{"text": "warm"}],
            "candidate_branch_codes": ["功能"],
            **updates,
        }
    )


class FakeJsonClient:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.messages = []
        self.settings = SimpleNamespace(cache_namespace="test", reasoning_effort="low")

    def generate_json(self, messages, **kwargs):
        self.messages.append(messages)
        payload = json.loads(messages[1]["content"])
        if "existing_facts" in payload:
            return JsonModelCallResult({"facts": []}, "test", {"total_tokens": 5})
        if "current_mappings" in payload:
            current = {
                mapping["fact_id"]: mapping for mapping in payload["current_mappings"]
            }
            return JsonModelCallResult(
                {
                    "adjudications": [
                        {
                            "fact_id": fact["fact_id"],
                            "label_code": (
                                (
                                    current[fact["fact_id"]]["label_codes"]
                                    or current[fact["fact_id"]].get(
                                        "candidate_label_codes", []
                                    )
                                )[0]
                                if (
                                    current[fact["fact_id"]]["label_codes"]
                                    or current[fact["fact_id"]].get(
                                        "candidate_label_codes", []
                                    )
                                )
                                else None
                            ),
                            "action": (
                                "ACCEPT"
                                if (
                                    current[fact["fact_id"]]["label_codes"]
                                    or current[fact["fact_id"]].get(
                                        "candidate_label_codes", []
                                    )
                                )
                                else (
                                    "REVIEW"
                                    if current[fact["fact_id"]]["disposition"]
                                    == "MAPPING_UNCERTAIN"
                                    else "ABSTAIN"
                                )
                            ),
                            "reason": "测试接受候选",
                        }
                        for fact in payload["facts"]
                    ]
                },
                "test",
                {"total_tokens": 5},
            )
        return JsonModelCallResult(next(self.payloads), "test", {"total_tokens": 5})


class CoverageJsonClient(FakeJsonClient):
    def __init__(self, payloads, coverage_payload):
        super().__init__(payloads)
        self.coverage_payload = coverage_payload

    def generate_json(self, messages, **kwargs):
        payload = json.loads(messages[1]["content"])
        if "existing_facts" in payload:
            self.messages.append(messages)
            return JsonModelCallResult(
                self.coverage_payload,
                "test",
                {"total_tokens": 5},
            )
        return super().generate_json(messages, **kwargs)


def test_coverage_audit_adds_omitted_fact_before_mapping(fact_taxonomy):
    existing = make_fact()
    omitted = make_fact(
        "b",
        opinion="商品表现不佳",
        sentiment="NEGATIVE",
        evidence_spans=[{"text": "cold"}],
    )
    original = existing.model_dump(mode="json")
    original["extraction_source"] = "COVERAGE"
    client = CoverageJsonClient(
        [
            {"facts": [original]},
            {
                "mappings": [
                    {"fact_id": "a", "label_codes": ["WARM"]},
                    {"fact_id": "b", "label_codes": ["COLD"]},
                ]
            },
        ],
        {"facts": [omitted.model_dump(mode="json")]},
    )

    result = classify_facts(
        comment="warm | cold",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )

    assert [fact.fact_id for fact in result.classification.extracted_facts] == [
        "a",
        "b",
    ]
    assert result.classification.extracted_facts[0].extraction_source == "PRIMARY"
    assert result.classification.extracted_facts[1].extraction_source == "COVERAGE"
    assert {unit.label_code for unit in result.classification.semantic_units} == {
        "WARM",
        "COLD",
    }
    assert result.metrics["coverage_audit_added_facts"] == 1


def test_coverage_accepts_atomic_facts_split_from_shared_evidence(fact_taxonomy):
    evidence = "warm and fits"
    existing = make_fact(
        opinion="商品同时保暖且合身",
        evidence_spans=[{"text": evidence}],
        candidate_branch_codes=["功能", "尺码"],
    )
    additions = {
        "facts": [
            make_fact(
                "b",
                opinion="商品保暖",
                evidence_spans=[{"text": evidence}],
            ).model_dump(mode="json"),
            make_fact(
                "c",
                opinion="商品合身",
                evidence_spans=[{"text": evidence}],
                candidate_branch_codes=["尺码"],
            ).model_dump(mode="json"),
        ]
    }

    result = merge_coverage_facts(
        [existing],
        additions,
        comment=evidence,
        taxonomy=fact_taxonomy,
    )

    assert result.added == 2
    assert result.rejected == 0
    assert [fact.opinion for fact in result.facts] == [
        "商品同时保暖且合身",
        "商品保暖",
        "商品合身",
    ]
    assert all(fact.evidence_spans[0].text == evidence for fact in result.facts)


def test_single_clause_multi_branch_fact_is_split_before_mapping(fact_taxonomy):
    evidence = "warm and fits"
    composite = make_fact(
        opinion="商品同时保暖且合身",
        evidence_spans=[{"text": evidence}],
        candidate_branch_codes=["功能", "尺码"],
    )
    warmth = make_fact(
        "b",
        opinion="商品保暖",
        evidence_spans=[{"text": evidence}],
    )
    fit = make_fact(
        "c",
        opinion="商品合身",
        evidence_spans=[{"text": evidence}],
        candidate_branch_codes=["尺码"],
    )
    client = CoverageJsonClient(
        [
            {"facts": [composite.model_dump(mode="json")]},
            {
                "mappings": [
                    {
                        "fact_id": "a",
                        "relation_type": "COVERED_BY",
                        "related_fact_ids": ["b", "c"],
                    },
                    {"fact_id": "b", "label_codes": ["WARM"]},
                    {"fact_id": "c", "label_codes": ["FIT"]},
                ]
            },
        ],
        {
            "facts": [
                warmth.model_dump(mode="json"),
                fit.model_dump(mode="json"),
            ]
        },
    )

    result = classify_facts(
        comment=evidence,
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )

    assert result.metrics["coverage_audit_calls"] == 1
    assert result.metrics["coverage_audit_added_facts"] == 2
    assert [fact.fact_id for fact in result.classification.extracted_facts] == [
        "a",
        "b",
        "c",
    ]
    assert {unit.label_code for unit in result.classification.semantic_units} == {
        "WARM",
        "FIT",
    }


def test_empty_extraction_triggers_coverage_audit(fact_taxonomy):
    recovered = make_fact()
    client = CoverageJsonClient(
        [
            {"facts": []},
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
        ],
        {"facts": [recovered.model_dump(mode="json")]},
    )

    result = classify_facts(
        comment="warm",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )

    assert result.metrics["coverage_audit_calls"] == 1
    assert result.metrics["coverage_audit_added_facts"] == 1
    assert [unit.label_code for unit in result.classification.semantic_units] == [
        "WARM"
    ]


@pytest.mark.parametrize("invalid_kind", ["duplicate", "evidence", "branch"])
def test_invalid_coverage_addition_safely_keeps_original_facts(
    fact_taxonomy,
    invalid_kind,
):
    existing = make_fact()
    addition = make_fact("b").model_dump(mode="json")
    if invalid_kind == "duplicate":
        addition["event_ref"] = "another-event"
        addition["fact_role"] = "EVIDENCE"
    elif invalid_kind == "evidence":
        addition["evidence_spans"] = [{"text": "not in comment", "source": "COMMENT"}]
    elif invalid_kind == "branch":
        addition["candidate_branch_codes"] = ["UNKNOWN_BRANCH"]
    client = CoverageJsonClient(
        [
            {"facts": [existing.model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
        ],
        {"facts": [addition]},
    )

    result = classify_facts(
        comment="warm; context",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )

    assert result.classification.extracted_facts == [existing]
    assert result.metrics["coverage_audit_failures"] == 1
    assert result.metrics["coverage_audit_added_facts"] == 0
    assert result.metrics["coverage_audit_rejected_facts"] == 1
    assert result.classification.needs_review
    diagnostic = result.classification.review_diagnostics[0]
    assert diagnostic.code == "COVERAGE_AUDIT_FAILED"
    assert diagnostic.action == "SYSTEM_RERUN"
    assert diagnostic.detail.startswith("覆盖审计候选事实未通过校验：")
    assert [unit.label_code for unit in result.classification.semantic_units] == [
        "WARM"
    ]


def test_coverage_audit_isolates_invalid_item_and_keeps_valid_item(fact_taxonomy):
    existing = make_fact()
    invalid = make_fact("bad").model_dump(mode="json")
    invalid["evidence_spans"] = [{"text": "missing", "source": "COMMENT"}]
    valid = make_fact(
        "good",
        opinion="商品表现不佳",
        sentiment="NEGATIVE",
        evidence_spans=[{"text": "cold"}],
    )
    client = CoverageJsonClient(
        [
            {"facts": [existing.model_dump(mode="json")]},
            {
                "mappings": [
                    {"fact_id": "a", "label_codes": ["WARM"]},
                    {"fact_id": "good", "label_codes": ["COLD"]},
                ]
            },
        ],
        {"facts": [invalid, valid.model_dump(mode="json")]},
    )

    result = classify_facts(
        comment="warm; cold",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )

    assert [fact.fact_id for fact in result.classification.extracted_facts] == [
        "a",
        "good",
    ]
    assert result.metrics["coverage_audit_added_facts"] == 1
    assert result.metrics["coverage_audit_rejected_facts"] == 1
    assert result.metrics["coverage_audit_failures"] == 1
    assert result.classification.needs_review
    diagnostic = result.classification.review_diagnostics[0]
    assert diagnostic.code == "COVERAGE_AUDIT_FAILED"
    assert diagnostic.evidence_text == "missing"
    assert diagnostic.action == "SYSTEM_RERUN"


def test_coverage_duplicate_identity_keeps_distinct_conditions(fact_taxonomy):
    existing = make_fact(condition="indoors")
    addition = make_fact("b", condition="outdoors")
    client = CoverageJsonClient(
        [
            {"facts": [existing.model_dump(mode="json")]},
            {
                "mappings": [
                    {"fact_id": "a", "label_codes": ["WARM"]},
                    {"fact_id": "b", "label_codes": ["WARM"]},
                ]
            },
        ],
        {"facts": [addition.model_dump(mode="json")]},
    )

    result = classify_facts(
        comment="warm; context",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )

    assert result.metrics["coverage_audit_added_facts"] == 1
    assert len(result.classification.semantic_units) == 2


def test_coverage_audit_failure_forces_manual_review(fact_taxonomy):
    existing = make_fact()
    client = CoverageJsonClient(
        [
            {"facts": [existing.model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
        ],
        {"invalid": []},
    )

    result = classify_facts(
        comment="warm; context",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )

    assert result.classification.needs_review
    assert any(
        "覆盖审计失败" in reason for reason in result.classification.review_reasons
    )
    assert result.metrics["coverage_audit_calls"] == 2
    assert result.metrics["coverage_audit_retries"] == 1
    assert result.metrics["coverage_audit_failures"] == 1


@pytest.mark.parametrize(
    "decision,disposition,needs_review",
    [
        ("ABSTAIN", "EXPECTED_ABSTENTION", False),
        ("REVIEW", "MAPPING_UNCERTAIN", True),
    ],
)
def test_evidence_label_adjudication_withdraws_only_existing_candidate(
    fact_taxonomy,
    decision,
    disposition,
    needs_review,
):
    fact = make_fact()
    classification = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["WARM"])]),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )

    result = compile_evidence_label_adjudications(
        classification,
        EvidenceLabelAdjudications(
            adjudications=[
                EvidenceLabelAdjudication(
                    fact_id="a",
                    label_code=None,
                    action=decision,
                    reason="独立裁决",
                )
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )

    assert result.semantic_units == []
    assert result.unknown_semantics[0].disposition == disposition
    assert result.needs_review is needs_review


def test_adjudication_can_replace_empty_mapping_without_stale_unknown(
    fact_taxonomy,
):
    fact = make_fact()
    classification = compile_fact_classification(
        [fact],
        FactMappings(
            mappings=[
                FactMapping(
                    fact_id="a",
                    disposition="TAXONOMY_GAP",
                    reason="初始映射遗漏",
                )
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )
    assert classification.unknown_semantics[0].fact_id == "a"

    result = compile_evidence_label_adjudications(
        classification,
        EvidenceLabelAdjudications(
            adjudications=[
                EvidenceLabelAdjudication(
                    fact_id="a",
                    action="REPLACE",
                    label_code="WARM",
                    reason="证据直接符合标签定义",
                )
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )

    assert [unit.label_code for unit in result.semantic_units] == ["WARM"]
    assert result.unknown_semantics == []
    assert result.fact_mappings[0].adjudication_action == "REPLACE"


@pytest.mark.parametrize(
    "action,label_code,expected_action,expected_disposition",
    [
        ("ACCEPT", None, "ACCEPT", None),
        ("REPLACE", "WARM", "ACCEPT", None),
        ("ABSTAIN", "WARM", "ABSTAIN", "EXPECTED_ABSTENTION"),
        ("REVIEW", "WARM", "REVIEW", "MAPPING_UNCERTAIN"),
    ],
)
def test_adjudication_format_errors_are_deterministically_normalized(
    fact_taxonomy,
    action,
    label_code,
    expected_action,
    expected_disposition,
):
    fact = make_fact()
    classification = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["WARM"])]),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )
    metrics = {}

    result = compile_evidence_label_adjudications(
        classification,
        EvidenceLabelAdjudications(
            adjudications=[
                EvidenceLabelAdjudication(
                    fact_id="a",
                    action=action,
                    label_code=label_code,
                    reason="独立裁决",
                )
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
        recovery_metrics=metrics,
    )

    mapping = result.fact_mappings[0]
    assert mapping.adjudication_action == expected_action
    assert mapping.disposition == expected_disposition
    assert "裁决格式已归一" in mapping.reason
    assert metrics == {"adjudication_format_recoveries": 1}


def test_empty_mapping_accept_with_unique_allowed_label_becomes_replace(
    fact_taxonomy,
):
    fact = make_fact()
    classification = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", disposition="TAXONOMY_GAP")]),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )

    result = compile_evidence_label_adjudications(
        classification,
        EvidenceLabelAdjudications(
            adjudications=[
                EvidenceLabelAdjudication(
                    fact_id="a",
                    action="ACCEPT",
                    label_code="WARM",
                    reason="证据直接符合标签定义",
                )
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )

    assert result.fact_mappings[0].adjudication_action == "REPLACE"
    assert result.fact_mappings[0].label_codes == ["WARM"]
    assert result.fact_mappings[0].disposition is None


@pytest.mark.parametrize("action,initial_code", [("ACCEPT", "WARM"), ("REPLACE", None)])
def test_adjudication_can_promote_independently_complete_evidence(
    fact_taxonomy,
    action,
    initial_code,
):
    fact = make_fact(fact_role="EVIDENCE")
    initial_mapping = FactMapping(
        fact_id="a",
        label_codes=[initial_code] if initial_code else [],
        disposition=None if initial_code else "EVIDENCE_ONLY",
    )
    classification = compile_fact_classification(
        [fact],
        FactMappings(mappings=[initial_mapping]),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )
    assert classification.semantic_units == []

    result = compile_evidence_label_adjudications(
        classification,
        EvidenceLabelAdjudications(
            adjudications=[
                EvidenceLabelAdjudication(
                    fact_id="a",
                    action=action,
                    label_code="WARM",
                    reason="原文自身完整表达可聚合属性",
                )
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )

    assert [unit.label_code for unit in result.semantic_units] == ["WARM"]
    assert result.semantic_units[0].fact_role == "EVIDENCE"
    assert result.semantic_units[0].decision_reason == "原文自身完整表达可聚合属性"
    assert result.fact_mappings[0].adjudication_action == action


def test_general_evaluation_and_ambiguous_experiencer_are_structural_gates(
    fact_taxonomy,
):
    facts = [
        make_fact("general", specificity="GENERAL_EVALUATION"),
        make_fact("ambiguous", experiencer_resolution="AMBIGUOUS"),
    ]
    result = compile_fact_classification(
        facts,
        FactMappings(
            mappings=[
                FactMapping(fact_id="general", label_codes=["WARM"]),
                FactMapping(fact_id="ambiguous", label_codes=["WARM"]),
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"general": ["WARM"], "ambiguous": ["WARM"]},
    )

    assert result.semantic_units == []
    assert [item.disposition for item in result.unknown_semantics] == [
        "EXPECTED_ABSTENTION",
        "MAPPING_UNCERTAIN",
    ]


@pytest.mark.parametrize("statement_type", ["EXPERIENCE", "EVALUATION"])
def test_uncertain_specific_feedback_is_expected_abstention(
    fact_taxonomy,
    statement_type,
):
    fact = make_fact(statement_type=statement_type, assertion="UNCERTAIN")
    result = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["WARM"])]),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )

    assert result.semantic_units == []
    assert result.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"
    assert result.fact_mappings[0].candidate_label_codes == ["WARM"]
    assert not result.needs_review


def test_uncertain_fact_remains_non_actionable_when_later_fact_is_affirmed(
    fact_taxonomy,
):
    comment = "It might feel cold. It feels cold."
    facts = [
        make_fact(
            "early",
            event_ref="tentative",
            statement_type="EVALUATION",
            assertion="UNCERTAIN",
            opinion="可能不保暖",
            sentiment="NEGATIVE",
            condition="on one device",
            evidence_spans=[{"text": comment}],
        ),
        make_fact(
            "later",
            event_ref="confirmed",
            statement_type="EXPERIENCE",
            fact_role="EVIDENCE",
            opinion="确实不保暖",
            sentiment="NEGATIVE",
            operation="use the feature",
            condition="on one device",
            evidence_spans=[{"text": "It feels cold."}],
        ),
    ]
    result = compile_fact_classification(
        facts,
        FactMappings(
            mappings=[
                FactMapping(fact_id="early", label_codes=["COLD"]),
                FactMapping(
                    fact_id="later",
                    label_codes=["COLD"],
                    adjudication_action="REPLACE",
                ),
            ]
        ),
        comment=comment,
        taxonomy=fact_taxonomy,
        allowed={"early": ["COLD"], "later": ["COLD"]},
    )

    assert [unit.label_code for unit in result.semantic_units] == ["COLD"]
    assert [item.fact_id for item in result.unknown_semantics] == ["early"]
    assert result.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"
    assert result.fact_mappings[0].candidate_label_codes == ["COLD"]
    assert result.fact_mappings[0].disposition == "EXPECTED_ABSTENTION"
    assert not result.needs_review


def test_uncertain_specific_feedback_is_not_suppressed_as_fallback(
    fact_taxonomy,
):
    rules = fact_taxonomy.validation_rules.model_copy(
        update={"fallback_label_codes": ["WARM"]}
    )
    taxonomy = fact_taxonomy.model_copy(update={"validation_rules": rules})
    fact = make_fact(assertion="UNCERTAIN")

    result = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["WARM"])]),
        comment="warm",
        taxonomy=taxonomy,
        allowed={"a": ["WARM"]},
    )

    assert result.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"
    assert not result.needs_review


def test_invalid_adjudication_output_falls_back_to_review(fact_taxonomy):
    class InvalidAdjudicationClient(FakeJsonClient):
        def generate_json(self, messages, **kwargs):
            payload = json.loads(messages[1]["content"])
            if "current_mappings" in payload:
                self.messages.append(messages)
                return JsonModelCallResult({"invalid": []}, "test", {"total_tokens": 5})
            return super().generate_json(messages, **kwargs)

    fact = make_fact(fact_role="EVIDENCE")
    client = InvalidAdjudicationClient(
        [
            {"facts": [fact.model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
        ]
    )

    result = classify_facts(
        comment="warm",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    ).classification

    assert result.semantic_units == []
    assert result.unknown_semantics[0].disposition == "MAPPING_UNCERTAIN"
    assert result.needs_review


def test_two_calls_map_only_selected_branch_and_cache(fact_taxonomy, tmp_path):
    fact = make_fact()
    client = FakeJsonClient(
        [
            {"facts": [fact.model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
        ]
    )
    kwargs = dict(
        comment="warm",
        model_name="test",
        thinking=False,
        messages=[],
        taxonomy=fact_taxonomy,
        claims=ListingClaimsConfig(version="none", claims=[]),
        client=client,
        cache=JsonlCache(tmp_path / "cache.jsonl"),
        force=False,
        classification_scope="test",
        model_policy_version="test",
    )
    result, cached = _call_with_cache(**kwargs)
    again, cached_again = _call_with_cache(**kwargs)

    assert not cached and cached_again
    assert result == again
    assert len(client.messages) == 2
    first = json.loads(client.messages[0][1]["content"])
    second = json.loads(client.messages[1][1]["content"])
    assert "labels" not in first
    assert {label["code"] for label in second["labels"]} == {"WARM", "COLD"}
    assert "基础操作能够完成只证明功能可用" in client.messages[1][0]["content"]
    assert "复合概括同时总结多个维度" in client.messages[1][0]["content"]
    assert result.usage == {"total_tokens": 10}
    assert result.metrics["fact_model_calls"] == 2
    assert result.metrics["coverage_audit_skips"] == 1
    assert result.metrics["evidence_adjudication_skips"] == 1
    assert result.classification.extracted_facts == [fact]


def test_different_objects_and_conditions_survive(fact_taxonomy):
    facts = [
        make_fact(product_ref="CURRENT:1"),
        make_fact(
            "b",
            product_ref="CURRENT:2",
            condition="湿冷时",
            opinion="湿冷时另一副手套冷",
            sentiment="NEGATIVE",
            evidence_spans=[{"text": "cold"}],
        ),
    ]
    result = compile_fact_classification(
        facts,
        FactMappings(
            mappings=[
                FactMapping(fact_id="a", label_codes=["WARM"]),
                FactMapping(fact_id="b", label_codes=["COLD"]),
            ]
        ),
        comment="warm then second pair cold",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"], "b": ["COLD"]},
    )
    assert len(result.semantic_units) == 2
    assert result.semantic_units[1].opinion == "湿冷时另一副手套冷"
    assert result.extracted_facts[1].product_ref == "CURRENT:2"


def test_semantic_unit_preserves_fact_context_and_evidence_source(fact_taxonomy):
    fact = make_fact(
        actor_ref="OTHER:1",
        product_ref="CURRENT:1",
        event_ref="第二次使用",
        statement_type="REPORTED",
        operation="打字",
        condition="户外打字",
        evidence_spans=[{"text": "warm", "source": "BODY"}],
    )
    result = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["WARM"])]),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )

    unit = result.semantic_units[0]
    assert unit.fact_id == "a"
    assert unit.fact_ids == ["a"]
    assert unit.actor_ref == "OTHER:1"
    assert unit.product_ref == "CURRENT:1"
    assert unit.event_ref == "第二次使用"
    assert unit.statement_type == "REPORTED"
    assert unit.operation == "打字"
    assert unit.condition == "户外打字"
    assert unit.evidence_source == "BODY"


@pytest.mark.parametrize(
    "statement", ["PREDICTION", "HYPOTHESIS", "INTENT", "NOT_TESTED", "ADVICE"]
)
def test_future_positive_is_not_confirmed(statement, fact_taxonomy):
    result = compile_fact_classification(
        [make_fact(statement_type=statement)],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["WARM"])]),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )
    assert result.semantic_units == []
    assert result.unknown_semantics[0].fact_id == "a"
    assert result.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"
    assert not result.needs_review


@pytest.mark.parametrize("mappings", [[], [FactMapping(fact_id="other")]])
def test_missing_or_foreign_fact_mapping_rejected(mappings, fact_taxonomy):
    with pytest.raises(ValueError, match="每个事实"):
        compile_fact_classification(
            [make_fact()],
            FactMappings(mappings=mappings),
            comment="warm",
            taxonomy=fact_taxonomy,
            allowed={"a": ["WARM"]},
        )


def test_unknown_preserves_fact_and_contiguous_evidence(fact_taxonomy):
    fact = make_fact(
        operation="打字",
        evidence_spans=[{"text": "warm"}, {"text": "today"}],
    )
    result = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", reason="没有对应标签")]),
        comment="warm and dry today",
        taxonomy=fact_taxonomy,
        allowed={"a": []},
    )
    assert result.unknown_semantics[0].evidence == "warm and dry today"
    assert result.unknown_semantics[0].disposition == "TAXONOMY_GAP"
    assert result.unknown_semantics[0].operation == "打字"
    assert result.extracted_facts == [fact]
    assert result.needs_review


def test_unmapped_disposition_cannot_hide_a_current_evaluation(fact_taxonomy):
    result = compile_fact_classification(
        [make_fact(statement_type="EVALUATION")],
        FactMappings(
            mappings=[
                FactMapping(
                    fact_id="a",
                    reason="忽略",
                    disposition="EXPECTED_ABSTENTION",
                )
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": []},
    )

    assert result.unknown_semantics[0].disposition == "MAPPING_UNCERTAIN"
    assert result.needs_review


def test_duplicate_summary_is_an_expected_abstention(fact_taxonomy):
    facts = [make_fact(), make_fact("b")]
    result = compile_fact_classification(
        facts,
        FactMappings(
            mappings=[
                FactMapping(fact_id="a", label_codes=["WARM"]),
                FactMapping(
                    fact_id="b",
                    reason="summary already represented",
                    relation_type="COVERED_BY",
                    related_fact_ids=["a"],
                ),
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"], "b": ["WARM"]},
    )

    assert result.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"
    assert not result.needs_review


def test_cross_dimension_summary_is_covered_by_all_specific_facts(fact_taxonomy):
    flexible = fact_taxonomy.labels[0].model_copy(
        update={"code": "FLEXIBLE", "name": "灵活"}
    )
    taxonomy = fact_taxonomy.model_copy(
        update={"labels": [*fact_taxonomy.labels, flexible]}
    )
    facts = [
        make_fact(),
        make_fact(
            "b",
            opinion="手套灵活",
            evidence_spans=[{"text": "flexible"}],
        ),
        make_fact(
            "summary",
            opinion="保暖与灵活平衡",
            evidence_spans=[{"text": "warm and flexible"}],
        ),
    ]
    result = compile_fact_classification(
        facts,
        FactMappings(
            mappings=[
                FactMapping(fact_id="a", label_codes=["WARM"]),
                FactMapping(fact_id="b", label_codes=["FLEXIBLE"]),
                FactMapping(
                    fact_id="summary",
                    relation_type="COVERED_BY",
                    related_fact_ids=["a", "b"],
                    reason="各维度已有具体事实共同覆盖",
                ),
            ]
        ),
        comment="warm and flexible",
        taxonomy=taxonomy,
        allowed={
            "a": ["WARM"],
            "b": ["FLEXIBLE"],
            "summary": ["WARM", "FLEXIBLE"],
        },
    )

    assert [unit.label_code for unit in result.semantic_units] == ["WARM", "FLEXIBLE"]
    assert result.fact_mappings[2].related_fact_ids == ["a", "b"]
    assert result.unknown_semantics[0].fact_id == "summary"
    assert result.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"
    assert not result.needs_review


@pytest.mark.parametrize(
    "statement_type,model_disposition",
    [
        ("NOT_TESTED", "MAPPING_UNCERTAIN"),
        ("PREDICTION", "TAXONOMY_GAP"),
    ],
)
def test_expected_abstention_overrides_model_disposition(
    fact_taxonomy, statement_type, model_disposition
):
    result = compile_fact_classification(
        [make_fact(statement_type=statement_type)],
        FactMappings(
            mappings=[
                FactMapping(
                    fact_id="a",
                    reason="模型错误处置",
                    disposition=model_disposition,
                )
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": []},
    )

    assert result.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"
    assert not result.needs_review


def test_recommendation_with_direct_label_forms_terminal(fact_taxonomy):
    result = compile_fact_classification(
        [make_fact(statement_type="RECOMMENDATION")],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["WARM"])]),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )

    assert [unit.label_code for unit in result.semantic_units] == ["WARM"]
    assert result.unknown_semantics == []
    assert result.fact_mappings[0].label_codes == ["WARM"]
    assert result.fact_mappings[0].disposition is None


@pytest.mark.parametrize(
    "fact_role,model_disposition",
    [
        ("EVIDENCE", "MAPPING_UNCERTAIN"),
        ("CONTEXT", "TAXONOMY_GAP"),
    ],
)
def test_context_role_overrides_model_disposition(
    fact_taxonomy, fact_role, model_disposition
):
    result = compile_fact_classification(
        [make_fact(fact_role=fact_role)],
        FactMappings(
            mappings=[
                FactMapping(
                    fact_id="a",
                    reason="模型错误处置",
                    disposition=model_disposition,
                )
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": []},
    )

    assert result.semantic_units == []
    assert [item.fact_id for item in result.unknown_semantics] == ["a"]
    assert result.unknown_semantics[0].disposition == "EVIDENCE_ONLY"
    assert not result.needs_review


def test_duplicate_abstention_overrides_model_uncertainty(fact_taxonomy):
    facts = [make_fact(), make_fact("b")]
    result = compile_fact_classification(
        facts,
        FactMappings(
            mappings=[
                FactMapping(fact_id="a", label_codes=["WARM"]),
                FactMapping(
                    fact_id="b",
                    reason="different wording in any language",
                    disposition="MAPPING_UNCERTAIN",
                    relation_type="COVERED_BY",
                    related_fact_ids=["a"],
                ),
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"], "b": ["WARM"]},
    )

    assert result.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"
    assert not result.needs_review


def test_fabricated_evidence_is_rejected_before_mapping(fact_taxonomy):
    client = FakeJsonClient([{"facts": [make_fact().model_dump(mode="json")]}] * 2)
    with pytest.raises(ValueError, match="证据不在"):
        classify_facts(
            comment="unrelated",
            taxonomy=fact_taxonomy,
            client=client,
            model_name="test",
            reasoning_effort="low",
        )
    assert len(client.messages) == 2


def test_branch_escape_is_rejected(fact_taxonomy):
    with pytest.raises(ValueError, match="分支外"):
        compile_fact_classification(
            [make_fact()],
            FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["FIT"])]),
            comment="warm",
            taxonomy=fact_taxonomy,
            allowed={"a": ["WARM"]},
        )


def test_old_output_without_fact_trace_remains_valid():
    assert ModelClassification.model_validate({}).extracted_facts == []


@pytest.mark.parametrize("statement", ["EXPERIENCE", "NEGATED"])
def test_negative_performance_is_not_negation_of_an_event(fact_taxonomy, statement):
    fact = make_fact(
        statement_type=statement,
        sentiment="NEGATIVE",
        opinion="手套不暖",
        evidence_spans=[{"text": "not warm"}],
    )
    result = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["COLD"])]),
        comment="not warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["COLD"]},
    )
    if statement == "EXPERIENCE":
        assert result.semantic_units[0].assertion == "AFFIRMED"
    else:
        assert result.semantic_units == []
        assert result.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"
    assert not result.needs_review


def test_reported_actual_experience_is_retained(fact_taxonomy):
    result = compile_fact_classification(
        [make_fact(statement_type="REPORTED", actor_ref="OTHER:1")],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["WARM"])]),
        comment="my child says warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )
    assert result.semantic_units[0].assertion == "AFFIRMED"
    assert result.extracted_facts[0].actor_ref == "OTHER:1"
    assert not result.needs_review


def test_reviewer_report_of_other_experiencer_is_retained(fact_taxonomy):
    fact = make_fact(
        actor_ref="OTHER:1",
        source_ref="REVIEWER",
        experiencer_ref="OTHER:1",
        experiencer_resolution="INHERITED",
        statement_type="REPORTED",
        evidence_spans=[{"text": "my husband said they kept his hands warm"}],
    )
    result = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["WARM"])]),
        comment="my husband said they kept his hands warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )

    assert result.semantic_units[0].source_ref == "REVIEWER"
    assert result.semantic_units[0].experiencer_ref == "OTHER:1"
    assert not result.needs_review


def test_one_atomic_fact_cannot_map_multiple_labels():
    with pytest.raises(ValueError):
        FactMapping(fact_id="a", label_codes=["WARM", "FIT"])


@pytest.mark.parametrize("different_event", [False, True])
def test_event_identity_deduplicates_only_same_event(fact_taxonomy, different_event):
    facts = [
        make_fact(),
        make_fact("b", event_ref="第二次使用" if different_event else "首次使用"),
    ]
    result = compile_fact_classification(
        facts,
        FactMappings(
            mappings=[
                FactMapping(fact_id=f.fact_id, label_codes=["WARM"]) for f in facts
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={f.fact_id: ["WARM"] for f in facts},
    )
    assert len(result.semantic_units) == (2 if different_event else 1)
    assert len(result.extracted_facts) == 2


def test_mapping_retries_only_failed_stage(fact_taxonomy):
    client = FakeJsonClient(
        [
            {"facts": [make_fact().model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["FIT"]}]},
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
        ]
    )
    result = classify_facts(
        comment="warm",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )
    assert len(client.messages) == 3
    assert result.metrics["fact_model_calls"] == 3
    assert result.metrics["fact_mapping_retries"] == 1
    assert result.usage["total_tokens"] == 15
    assert "上次输出未通过校验" in client.messages[2][-1]["content"]


def test_mapping_model_cannot_overwrite_program_audit_fields(fact_taxonomy):
    client = FakeJsonClient(
        [
            {"facts": [make_fact().model_dump(mode="json")]},
            {
                "mappings": [
                    {
                        "fact_id": "a",
                        "label_codes": ["WARM"],
                        "candidate_label_codes": ["WARM"],
                        "adjudication_action": "ACCEPT",
                    }
                ]
            },
        ]
    )

    result = classify_facts(
        comment="warm",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )

    mapping = result.classification.fact_mappings[0]
    assert mapping.label_codes == ["WARM"]
    assert mapping.candidate_label_codes == []
    mapping_payload = json.loads(client.messages[1][1]["content"])
    serialized_schema = json.dumps(mapping_payload["schema"])
    assert "candidate_label_codes" not in serialized_schema
    assert "adjudication_action" not in serialized_schema


def test_repeated_mapping_direction_error_keeps_other_valid_fact(fact_taxonomy):
    facts = [
        make_fact(),
        make_fact(
            "b",
            sentiment="NEGATIVE",
            opinion="不保暖",
            evidence_spans=[{"text": "cold"}],
        ),
    ]
    invalid_mapping = {
        "mappings": [
            {
                "fact_id": "a",
                "label_codes": ["WARM"],
                "candidate_label_codes": ["WARM"],
                "adjudication_action": "ACCEPT",
            },
            {
                "fact_id": "b",
                "label_codes": ["WARM"],
                "candidate_label_codes": ["WARM"],
                "adjudication_action": "ACCEPT",
            },
        ]
    }
    client = FakeJsonClient(
        [
            {"facts": [fact.model_dump(mode="json") for fact in facts]},
            invalid_mapping,
            invalid_mapping,
        ]
    )

    result = classify_facts(
        comment="warm but cold",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    ).classification

    assert [unit.fact_id for unit in result.semantic_units] == ["a"]
    assert result.unknown_semantics[0].fact_id == "b"
    assert result.unknown_semantics[0].disposition == "MAPPING_UNCERTAIN"
    assert result.needs_review
    assert len(client.messages) == 5


@pytest.mark.parametrize(
    "fact_role,relation_type,expected_disposition,expected_unknowns",
    [
        ("EVIDENCE", "SUPPORTS", "EXPECTED_ABSTENTION", 1),
        ("CONCLUSION", "COVERED_BY", "MAPPING_UNCERTAIN", 1),
    ],
)
def test_repeated_cross_event_relation_error_is_isolated(
    fact_taxonomy,
    fact_role,
    relation_type,
    expected_disposition,
    expected_unknowns,
):
    facts = [
        make_fact(),
        make_fact(
            "b",
            fact_role=fact_role,
            event_ref="另一次使用",
            evidence_spans=[{"text": "detail"}],
        ),
    ]
    invalid_mapping = {
        "mappings": [
            {"fact_id": "a", "label_codes": ["WARM"]},
            {
                "fact_id": "b",
                "relation_type": relation_type,
                "related_fact_ids": ["a"],
            },
        ]
    }
    client = FakeJsonClient(
        [
            {"facts": [fact.model_dump(mode="json") for fact in facts]},
            invalid_mapping,
            invalid_mapping,
        ]
    )

    result = classify_facts(
        comment="warm and detail",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    ).classification

    assert [unit.fact_id for unit in result.semantic_units] == ["a"]
    assert result.fact_mappings[1].relation_type == "NONE"
    assert result.fact_mappings[1].disposition == expected_disposition
    assert len(result.unknown_semantics) == expected_unknowns
    assert result.needs_review is (expected_disposition == "MAPPING_UNCERTAIN")
    assert len(client.messages) == 4


def test_invalid_part_retries_extraction_before_mapping(fact_taxonomy):
    client = FakeJsonClient(
        [
            {"facts": [make_fact(part="INVALID").model_dump(mode="json")]},
            {"facts": [make_fact().model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
        ]
    )
    result = classify_facts(
        comment="warm",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )
    assert result.metrics["fact_model_calls"] == 4
    assert result.metrics["fact_extraction_retries"] == 1
    assert result.metrics["coverage_audit_calls"] == 1
    assert "事实部位不适用" in client.messages[1][-1]["content"]
    assert result.classification.semantic_units[0].part == "UNSPECIFIED"


@pytest.mark.parametrize(
    "updates",
    [
        {"actor_ref": "买家"},
        {"actor_ref": "CURRENT"},
        {"actor_ref": "OTHER:"},
        {"actor_ref": "OTHER:my child"},
        {"product_ref": "本品"},
        {"product_ref": "OTHER:missing product"},
        {"product_ref": "CURRENT: "},
        {"actor_ref": "OTHER:0"},
        {"actor_ref": "OTHER:01"},
        {"actor_ref": "OTHER:-1"},
        {"actor_ref": "OTHER:1.5"},
        {"product_ref": "OTHER:１"},
        {"product_ref": "CURRENT:0"},
        {"product_ref": "CURRENT:01"},
    ],
)
def test_invalid_reference_repairs_only_extraction(fact_taxonomy, updates):
    client = FakeJsonClient(
        [
            {"facts": [make_fact(**updates).model_dump(mode="json")]},
            {"facts": [make_fact().model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
        ]
    )
    result = classify_facts(
        comment="warm",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )
    assert result.metrics["fact_model_calls"] == 4
    assert result.metrics["fact_extraction_retries"] == 1
    assert result.metrics["coverage_audit_calls"] == 1
    assert "事实对象引用不符合协议" in client.messages[1][-1]["content"]
    assert result.classification.extracted_facts[0].actor_ref == "REVIEWER"
    assert result.classification.extracted_facts[0].product_ref == "CURRENT"


def test_other_product_numeric_reference_retains_evidence(fact_taxonomy):
    fact = make_fact(
        product_ref="OTHER:1", evidence_spans=[{"text": "old gloves were warm"}]
    )
    result = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", reason="其他商品对照")]),
        comment="old gloves were warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )
    assert result.extracted_facts[0].product_ref == "OTHER:1"
    assert result.extracted_facts[0].evidence_spans[0].text == "old gloves were warm"
    assert result.semantic_units == []
    assert result.unknown_semantics[0].disposition == "OUT_OF_SCOPE"
    assert not result.needs_review


def test_current_single_and_numbered_references_cannot_mix(fact_taxonomy):
    facts = [make_fact(), make_fact("b", product_ref="CURRENT:1")]
    with pytest.raises(ValueError, match="不能与多件商品"):
        compile_fact_classification(
            facts,
            FactMappings(mappings=[FactMapping(fact_id=f.fact_id) for f in facts]),
            comment="warm",
            taxonomy=fact_taxonomy,
            allowed={f.fact_id: [] for f in facts},
        )


def test_service_responsibility_does_not_change_reviewer_reference(fact_taxonomy):
    fact = make_fact(subject="SERVICE", actor_ref="REVIEWER")
    client = FakeJsonClient(
        [
            {"facts": [fact.model_dump(mode="json")]},
            {
                "mappings": [
                    {"fact_id": "a", "label_codes": [], "reason": "无对应服务标签"}
                ]
            },
        ]
    )
    result = classify_facts(
        comment="warm",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )
    extracted = result.classification.extracted_facts[0]
    assert extracted.subject == "SERVICE"
    assert extracted.actor_ref == "REVIEWER"
    system = client.messages[0][0]["content"]
    assert "首次出现顺序编号" in system
    assert "actor与product编号互相独立" in system
    assert "评论者本人经历客服响应时actor_ref仍为REVIEWER" in system


def test_other_product_mapping_is_repaired_without_reextracting(fact_taxonomy):
    fact = make_fact(product_ref="OTHER:1")
    client = FakeJsonClient(
        [
            {"facts": [fact.model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
            {"mappings": [{"fact_id": "a", "label_codes": [], "reason": "对照商品"}]},
        ]
    )
    result = classify_facts(
        comment="previous pair was warm",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )
    assert result.metrics["fact_model_calls"] == 3
    assert result.classification.semantic_units == []
    assert result.classification.extracted_facts == [fact]
    mapping_input = json.loads(client.messages[2][1]["content"])
    assert mapping_input["allowed_labels_by_fact"]["a"] == []


def test_routing_exposes_topics_hidden_by_generic_branch_names(fact_taxonomy):
    fact_taxonomy.labels[0].group = "综合"
    client = FakeJsonClient(
        [
            {
                "facts": [
                    make_fact(candidate_branch_codes=["综合"]).model_dump(mode="json")
                ]
            },
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
        ]
    )
    classify_facts(
        comment="warm",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )
    extraction_input = json.loads(client.messages[0][1]["content"])
    branch = extraction_input["candidate_branches"]["综合"]
    assert branch == {"name": "综合", "topics": ["保暖"]}
    assert "WARM" not in json.dumps(extraction_input["candidate_branches"])


def test_prediction_cannot_hide_later_confirmed_fact(fact_taxonomy):
    facts = [make_fact(statement_type="PREDICTION"), make_fact("b")]
    result = compile_fact_classification(
        facts,
        FactMappings(
            mappings=[
                FactMapping(fact_id=f.fact_id, label_codes=["WARM"]) for f in facts
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={f.fact_id: ["WARM"] for f in facts},
    )
    assert [unit.assertion for unit in result.semantic_units] == ["AFFIRMED"]
    assert result.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"


def test_claims_require_explicit_safe_review(fact_taxonomy):
    claims = ListingClaimsConfig.model_validate(
        {
            "version": "test",
            "claims": [
                {
                    "claim_id": "c",
                    "text": "保暖",
                    "source": "测试",
                    "allowed_label_codes": ["WARM"],
                }
            ],
        }
    )
    client = FakeJsonClient(
        [
            {"facts": [make_fact().model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
        ]
    )
    result = classify_facts(
        comment="warm",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
        claims=claims,
    )
    assert result.classification.needs_review
    assert any("Listing" in reason for reason in result.classification.review_reasons)


def test_boundary_required_labels_are_optional_and_checked(fact_taxonomy):
    assert fact_taxonomy.validation_rules.boundary_required_labels == []
    data = fact_taxonomy.model_dump(mode="json")
    data["validation_rules"]["boundary_required_labels"] = ["MISSING"]
    with pytest.raises(ValueError, match="未知标签"):
        TaxonomyConfig.model_validate(data)


def test_fallback_label_codes_are_optional_and_checked(fact_taxonomy):
    assert fact_taxonomy.validation_rules.fallback_label_codes == []
    data = fact_taxonomy.model_dump(mode="json")
    data["validation_rules"]["fallback_label_codes"] = ["MISSING"]
    with pytest.raises(ValueError, match="未知标签"):
        TaxonomyConfig.model_validate(data)


@pytest.mark.parametrize(
    "comment,sentiment,statement,label_name",
    [
        ("我习惯选择宽一点的规格。", "NEUTRAL", "EVALUATION", "尺码需求"),
        ("收到的尺寸太小，挤得不舒服。", "NEGATIVE", "EXPERIENCE", "偏小"),
        ("戴上后大小刚好。", "POSITIVE", "EVALUATION", "合身"),
    ],
)
def test_sizing_directions_survive_two_stage_mapping(
    fact_taxonomy, comment, sentiment, statement, label_name
):
    data = fact_taxonomy.model_dump(mode="json")
    data["labels"] = [
        {
            "code": "SIZE",
            "name": label_name,
            "group": "尺码",
            "allowed_sentiments": [sentiment],
        }
    ]
    taxonomy = TaxonomyConfig.model_validate(data)
    fact = make_fact(
        opinion=comment,
        sentiment=sentiment,
        statement_type=statement,
        evidence_spans=[{"text": comment}],
        candidate_branch_codes=["尺码"],
    )
    client = FakeJsonClient(
        [
            {"facts": [fact.model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["SIZE"]}]},
        ]
    )
    result = classify_facts(
        comment=comment,
        taxonomy=taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )
    unit = result.classification.semantic_units[0]
    assert unit.sentiment == sentiment
    assert unit.assertion == "AFFIRMED"
    assert result.classification.unknown_semantics == []
    instruction = client.messages[0][0]["content"]
    assert "个人选码偏好或本人尺码需求，其sentiment为NEUTRAL" in instruction
    assert "尺码问题仍为NEGATIVE" in instruction
    assert "当前商品合身仍为POSITIVE" in instruction


@pytest.mark.parametrize(
    "previous_version",
    [
        "category-fact-v2-v2",
        "category-fact-v2-v3",
        "category-fact-v2-v4",
        "category-fact-v2-v12",
        "category-fact-v2-v13",
        "category-fact-v2-v14",
        "category-fact-v2-v15",
        "category-fact-v2-v16",
        "category-fact-v2-v17",
        "category-fact-v2-v18",
        "category-fact-v2-v19",
        "category-fact-v2-v20",
        "category-fact-v2-v21",
        "category-fact-v2-v22",
        "category-fact-v2-v23",
        "category-fact-v2-v24",
        "category-fact-v2-v25",
        "category-fact-v2-v26",
        "category-fact-v2-v27",
        "category-fact-v2-v28",
        "category-fact-v2-v29",
        "category-fact-v2-v30",
    ],
)
def test_fact_prompt_update_invalidates_previous_fact_cache(
    fact_taxonomy, monkeypatch, previous_version
):
    with monkeypatch.context() as context:
        context.setattr(prompt, "prompt_version", lambda _: previous_version)
        old_fingerprint = prompt.recognition_fingerprint(fact_taxonomy)
    assert prompt.prompt_version(fact_taxonomy) == "category-fact-v2-v31"
    assert old_fingerprint != prompt.recognition_fingerprint(fact_taxonomy)


@pytest.mark.parametrize(
    "comment,statement,label_name",
    [
        ("The fabric felt coarse last spring.", "EVALUATION", "粗糙"),
        ("The seam tore during yesterday's walk.", "EXPERIENCE", "开线"),
    ],
)
def test_past_attribute_and_event_keep_distinct_fact_states(
    fact_taxonomy, comment, statement, label_name
):
    data = fact_taxonomy.model_dump(mode="json")
    data["labels"] = [
        {
            "code": "DETAIL",
            "name": label_name,
            "group": "质量",
            "allowed_sentiments": ["NEGATIVE"],
        }
    ]
    taxonomy = TaxonomyConfig.model_validate(data)
    fact = make_fact(
        opinion=comment,
        sentiment="NEGATIVE",
        statement_type=statement,
        evidence_spans=[{"text": comment}],
        candidate_branch_codes=["质量"],
    )
    client = FakeJsonClient(
        [
            {"facts": [fact.model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["DETAIL"]}]},
        ]
    )
    result = classify_facts(
        comment=comment,
        taxonomy=taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )
    assert result.classification.extracted_facts[0].statement_type == statement
    assert result.classification.semantic_units[0].assertion == "AFFIRMED"
    instruction = client.messages[0][0]["content"]
    assert "主观判断，不受现在或过去时限制" in instruction
    assert "不足以把属性评价变成体验事件" in instruction


@pytest.mark.parametrize("different_condition", [False, True])
def test_same_identity_merges_details_but_preserves_conditions(
    fact_taxonomy, different_condition
):
    facts = [
        make_fact(opinion="initial warmth"),
        make_fact(
            "b",
            opinion="later warmth",
            condition="later" if different_condition else "",
            evidence_spans=[{"text": "still warm"}],
        ),
    ]
    result = compile_fact_classification(
        facts,
        FactMappings(
            mappings=[
                FactMapping(fact_id=f.fact_id, label_codes=["WARM"]) for f in facts
            ]
        ),
        comment="warm, and still warm",
        taxonomy=fact_taxonomy,
        allowed={f.fact_id: ["WARM"] for f in facts},
    )
    assert len(result.semantic_units) == (2 if different_condition else 1)
    if not different_condition:
        assert result.semantic_units[0].fact_ids == ["a", "b"]
        assert result.semantic_units[0].evidence == "warm, and still warm"
        assert "initial warmth" in result.semantic_units[0].opinion
        assert "later warmth" in result.semantic_units[0].opinion


@pytest.mark.parametrize("profile,expected", [("fact_v2", 2), ("semantic_v1", 1)])
def test_final_validator_preserves_fact_identity_only_for_fact_v2(
    fact_taxonomy, profile, expected
):
    from return_semantics.validator import validate_classification

    facts = [
        make_fact(product_ref="CURRENT:1"),
        make_fact("b", product_ref="CURRENT:2"),
    ]
    compiled = compile_fact_classification(
        facts,
        FactMappings(
            mappings=[
                FactMapping(fact_id=f.fact_id, label_codes=["WARM"]) for f in facts
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={f.fact_id: ["WARM"] for f in facts},
    )
    result = validate_classification(
        "test",
        "warm",
        "",
        compiled,
        fact_taxonomy.model_copy(update={"recognition_profile": profile}),
        ListingClaimsConfig(version="none", claims=[]),
        "test",
        "test",
        "review",
    )
    assert len(result.semantic_units) == expected


@pytest.mark.parametrize(
    "statement,primary",
    [("EXPERIENCE", True), ("EXPERIENCE", False), ("PREDICTION", True)],
)
def test_primary_requires_explicit_and_confirmed_fact(
    fact_taxonomy, statement, primary
):
    fact = make_fact(statement_type=statement, is_primary_reason=primary)
    result = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["WARM"])]),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )
    assert result.primary_label_codes == (
        ["WARM"] if primary and statement == "EXPERIENCE" else []
    )
    assert make_fact().is_primary_reason is False


@pytest.mark.parametrize("name", ["愿意回购", "值得购买", "保暖"])
def test_intent_is_always_expected_abstention(fact_taxonomy, name):
    label = fact_taxonomy.labels[0].model_copy(update={"name": name})
    taxonomy = fact_taxonomy.model_copy(update={"labels": [label]})
    result = compile_fact_classification(
        [make_fact(statement_type="INTENT")],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["WARM"])]),
        comment="warm",
        taxonomy=taxonomy,
        allowed={"a": ["WARM"]},
    )
    assert result.semantic_units == []
    assert result.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"


def test_negative_repurchase_intent_is_expected_abstention(fact_taxonomy):
    from return_semantics.validator import validate_classification

    label = fact_taxonomy.labels[1].model_copy(update={"name": "不值得购买/拒绝回购"})
    taxonomy = fact_taxonomy.model_copy(update={"labels": [label]})
    fact = make_fact(
        statement_type="INTENT",
        sentiment="NEGATIVE",
        opinion="明确拒绝回购",
        evidence_spans=[{"text": "I would not buy again."}],
    )
    compiled = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["COLD"])]),
        comment="I would not buy again.",
        taxonomy=taxonomy,
        allowed={"a": ["COLD"]},
    )
    result = validate_classification(
        "test",
        "I would not buy again.",
        "",
        compiled,
        taxonomy,
        ListingClaimsConfig(version="none", claims=[]),
        "test",
        "test",
        "review",
    )
    assert result.semantic_units == []
    assert result.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"


def test_fact_extraction_requests_explicit_primary_and_no_anatomical_inference(
    fact_taxonomy,
):
    from return_semantics.fact_pipeline import extraction_messages

    instruction = extraction_messages("ordinary review", fact_taxonomy)[0]["content"]
    for boundary in (
        "is_primary_reason默认false",
        "整体尺码陈述",
        "hand、grip、touchscreen",
        "雪天、雨天",
        "当前态度",
    ):
        assert boundary in instruction


@pytest.mark.parametrize(
    "product,sentiment,expected",
    [
        ("CURRENT", "POSITIVE", ["WARM", "COLD", "OTHER_POS"]),
        ("CURRENT", "NEGATIVE", ["WARM", "COLD", "OTHER_NEG"]),
        ("OTHER:1", "POSITIVE", []),
    ],
)
def test_current_product_receives_direction_compatible_fallback(
    fact_taxonomy, product, sentiment, expected
):
    from return_semantics.fact_pipeline import _mapping_payload

    positive = fact_taxonomy.labels[0].model_copy(
        update={"code": "OTHER_POS", "name": "其他", "group": "兜底"}
    )
    negative = fact_taxonomy.labels[1].model_copy(
        update={"code": "OTHER_NEG", "name": "其他", "group": "兜底"}
    )
    rules = fact_taxonomy.validation_rules.model_copy(
        update={"fallback_label_codes": ["OTHER_POS", "OTHER_NEG"]}
    )
    taxonomy = fact_taxonomy.model_copy(
        update={
            "labels": [*fact_taxonomy.labels, positive, negative],
            "validation_rules": rules,
        }
    )
    payload = _mapping_payload(
        [make_fact(product_ref=product, sentiment=sentiment)], taxonomy
    )
    assert payload["allowed_labels_by_fact"]["a"] == expected
    assert {label["code"] for label in payload["labels"]} == set(expected)


def test_unrouted_current_fact_can_reach_existing_other_label(fact_taxonomy):
    from return_semantics.fact_pipeline import _mapping_payload

    fallback = fact_taxonomy.labels[0].model_copy(
        update={"code": "OTHER", "name": "其他", "group": "兜底"}
    )
    rules = fact_taxonomy.validation_rules.model_copy(
        update={"fallback_label_codes": ["OTHER"]}
    )
    taxonomy = fact_taxonomy.model_copy(
        update={
            "labels": [*fact_taxonomy.labels, fallback],
            "validation_rules": rules,
        }
    )
    payload = _mapping_payload([make_fact(candidate_branch_codes=[])], taxonomy)
    assert payload["allowed_labels_by_fact"]["a"] == ["OTHER"]


def test_specific_label_suppresses_configured_fallback_in_same_scope(
    fact_taxonomy,
):
    fallback = fact_taxonomy.labels[0].model_copy(
        update={"code": "FALLBACK", "name": "概括评价", "group": "综合"}
    )
    rules = fact_taxonomy.validation_rules.model_copy(
        update={"fallback_label_codes": ["FALLBACK"]}
    )
    taxonomy = fact_taxonomy.model_copy(
        update={
            "labels": [*fact_taxonomy.labels, fallback],
            "validation_rules": rules,
        }
    )
    facts = [make_fact(), make_fact("b")]

    result = compile_fact_classification(
        facts,
        FactMappings(
            mappings=[
                FactMapping(fact_id="a", label_codes=["WARM"]),
                FactMapping(
                    fact_id="b",
                    label_codes=["FALLBACK"],
                    fallback_is_independent=True,
                ),
            ]
        ),
        comment="warm",
        taxonomy=taxonomy,
        allowed={"a": ["WARM"], "b": ["FALLBACK"]},
    )

    assert [unit.label_code for unit in result.semantic_units] == ["WARM"]
    assert result.semantic_units[0].fact_ids == ["a"]
    fallback_mapping = next(
        mapping for mapping in result.fact_mappings if mapping.fact_id == "b"
    )
    assert fallback_mapping.label_codes == []
    assert fallback_mapping.candidate_label_codes == ["FALLBACK"]
    assert fallback_mapping.disposition == "EXPECTED_ABSTENTION"


def test_independent_fallback_remains_for_distinct_evidence(fact_taxonomy):
    fallback = fact_taxonomy.labels[0].model_copy(
        update={"code": "FALLBACK", "name": "概括评价", "group": "综合"}
    )
    rules = fact_taxonomy.validation_rules.model_copy(
        update={"fallback_label_codes": ["FALLBACK"]}
    )
    taxonomy = fact_taxonomy.model_copy(
        update={
            "labels": [*fact_taxonomy.labels, fallback],
            "validation_rules": rules,
        }
    )
    facts = [
        make_fact(),
        make_fact(
            "b",
            event_ref="另一次使用",
            evidence_spans=[{"text": "independent opinion"}],
        ),
    ]

    result = compile_fact_classification(
        facts,
        FactMappings(
            mappings=[
                FactMapping(fact_id="a", label_codes=["WARM"]),
                FactMapping(
                    fact_id="b",
                    label_codes=["FALLBACK"],
                    fallback_is_independent=True,
                ),
            ]
        ),
        comment="warm and independent opinion",
        taxonomy=taxonomy,
        allowed={"a": ["WARM"], "b": ["FALLBACK"]},
    )

    assert [unit.label_code for unit in result.semantic_units] == [
        "WARM",
        "FALLBACK",
    ]


def test_non_independent_fallback_is_normal_abstention(fact_taxonomy):
    fallback = fact_taxonomy.labels[0].model_copy(update={"code": "FALLBACK"})
    taxonomy = fact_taxonomy.model_copy(
        update={
            "labels": [*fact_taxonomy.labels, fallback],
            "validation_rules": fact_taxonomy.validation_rules.model_copy(
                update={"fallback_label_codes": ["FALLBACK"]}
            ),
        }
    )

    result = compile_fact_classification(
        [make_fact()],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["FALLBACK"])]),
        comment="warm",
        taxonomy=taxonomy,
        allowed={"a": ["FALLBACK"]},
    )

    assert result.semantic_units == []
    assert result.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"
    assert not result.needs_review


def test_duplicate_fallback_facts_are_merged_across_model_event_splits(fact_taxonomy):
    fallback = fact_taxonomy.labels[0].model_copy(update={"code": "FALLBACK"})
    taxonomy = fact_taxonomy.model_copy(
        update={
            "labels": [*fact_taxonomy.labels, fallback],
            "validation_rules": fact_taxonomy.validation_rules.model_copy(
                update={"fallback_label_codes": ["FALLBACK"]}
            ),
        }
    )
    facts = [make_fact(), make_fact("b", event_ref="MODEL_SPLIT")]

    result = compile_fact_classification(
        facts,
        FactMappings(
            mappings=[
                FactMapping(
                    fact_id=fact.fact_id,
                    label_codes=["FALLBACK"],
                    fallback_is_independent=True,
                )
                for fact in facts
            ]
        ),
        comment="warm",
        taxonomy=taxonomy,
        allowed={fact.fact_id: ["FALLBACK"] for fact in facts},
    )

    assert [unit.label_code for unit in result.semantic_units] == ["FALLBACK"]
    assert set(result.semantic_units[0].fact_ids) == {"a", "b"}


def test_uncertain_fact_and_inferred_mapping_cannot_form_terminal_label(
    fact_taxonomy,
):
    uncertain = compile_fact_classification(
        [make_fact(assertion="UNCERTAIN")],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["WARM"])]),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )
    inferred = compile_fact_classification(
        [make_fact()],
        FactMappings(
            mappings=[
                FactMapping(
                    fact_id="a",
                    label_codes=["WARM"],
                    evidence_relation="INFERRED",
                )
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )

    assert uncertain.semantic_units == []
    assert uncertain.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"
    assert not uncertain.needs_review
    assert inferred.semantic_units == []
    assert inferred.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"
    assert not inferred.needs_review


def test_expected_abstention_precedes_inferred_mapping_review(fact_taxonomy):
    result = compile_fact_classification(
        [make_fact(statement_type="PREDICTION")],
        FactMappings(
            mappings=[
                FactMapping(
                    fact_id="a",
                    label_codes=["WARM"],
                    evidence_relation="INFERRED",
                )
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )

    assert result.semantic_units == []
    assert result.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"
    assert not result.needs_review


def test_fact_prompts_define_participant_certainty_and_entailment_contracts(
    fact_taxonomy,
):
    client = FakeJsonClient(
        [
            {"facts": [make_fact(fact_role="EVIDENCE").model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
        ]
    )

    classify_facts(
        comment="warm; context",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )

    extraction_instruction = client.messages[0][0]["content"]
    coverage_instruction = client.messages[1][0]["content"]
    mapping_instruction = client.messages[2][0]["content"]
    adjudication_instruction = client.messages[3][0]["content"]
    assert "不得因换句、换属性或换event_ref自动切回REVIEWER" in extraction_instruction
    assert "只有更换体验者会改变事实真值或业务作用域时" in extraction_instruction
    assert "后文才首次出现的其他人物不能反向制造" in extraction_instruction
    assert "随后无新主语的穿戴、合身或使用结果可继承该人" in extraction_instruction
    assert "assertion表示命题确定性" in extraction_instruction
    assert "体验结果的确定性与原因归属的确定性是两个独立判断" in extraction_instruction
    assert "原因无法确认时使用causal_attribution=UNKNOWN" in extraction_instruction
    assert "按话语更新合为后文的AFFIRMED结论" in extraction_instruction
    assert "每个事实只能表达一个可独立归类的观点" in extraction_instruction
    assert "剩余内容若仍可独立判断" in extraction_instruction
    assert "condition只保留时间、场景、程度" in extraction_instruction
    assert "做工好、材质好、轻便、灵活、穿脱方便" in extraction_instruction
    assert "直接表达轻便、灵活、做工、穿脱或某项操作可完成时" in extraction_instruction
    assert "即使使用will、sooner or later等措辞" in extraction_instruction
    assert "某尺码适合大多数人、介于两个尺码时建议选大一码" in extraction_instruction
    assert "逐句检查独立属性、性能、尺码与部位" in coverage_instruction
    assert "不能因已有事实覆盖了整句" in coverage_instruction
    assert "该事实不是原子事实，不能视为已覆盖" in coverage_instruction
    assert "拆分后的事实允许共用同一原文证据" in coverage_instruction
    assert "condition不得重复product_ref" in coverage_instruction
    assert "未实际购买、穿戴或测试的备选规格" in coverage_instruction
    assert "不能因原因归属不确定而降低已发生结果的确定性" in coverage_instruction
    assert "evidence_relation必须按逻辑支持关系填写" in mapping_instruction
    assert "fallback_is_independent=true" in mapping_instruction
    assert "related_fact_ids列出共同覆盖它的全部具体事实" in mapping_instruction
    assert "不能因单一标签无法同时表达多个维度而二选一" in mapping_instruction
    assert "不得因已有更具体的质量标签而删除可用性" in mapping_instruction
    assert "原因归属不确定不能成为弃权理由" in mapping_instruction
    assert "证据明确不蕴含候选标签时ABSTAIN" in adjudication_instruction
    assert "原因归属不确定不能把已发生的体验结果降级" in adjudication_instruction
    assert (
        "完成操作的直接EVIDENCE本身就是可独立聚合的可用性事实"
        in adjudication_instruction
    )
    assert "只有证据本身确有两种合理解释" in adjudication_instruction
    assert "直接陈述的商品固有结构、材质或客观能力" in adjudication_instruction
    assert "依赖具体体验者的主观感受" in adjudication_instruction
    assert (
        "评论者转述OTHER:n的已发生使用体验仍是有效用户反馈" in adjudication_instruction
    )
    assert "后文才出现的其他人物不能反向" in adjudication_instruction
    assert "不能把明确不支持标签的候选送人工复核" in adjudication_instruction


@pytest.mark.parametrize(
    "profile,explicit,expected",
    [
        ("fact_v2", False, []),
        ("fact_v2", True, ["COLD"]),
        ("semantic_v1", False, ["COLD"]),
    ],
)
def test_primary_projection_requires_explicit_fact_only_in_fact_v2(
    fact_taxonomy, profile, explicit, expected
):
    from return_semantics.validator import validate_classification

    fact = make_fact(sentiment="NEGATIVE", is_primary_reason=explicit)
    taxonomy = fact_taxonomy.model_copy(update={"recognition_profile": profile})
    compiled = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["COLD"])]),
        comment="warm",
        taxonomy=taxonomy,
        allowed={"a": ["COLD"]},
    )
    result = validate_classification(
        "test",
        "warm",
        "",
        compiled,
        taxonomy,
        ListingClaimsConfig(version="none", claims=[]),
        "test",
        "test",
        "review",
    )
    assert result.primary_label_codes == expected
    if profile == "fact_v2" and not explicit:
        compiled.primary_label_codes = ["COLD"]
        result = validate_classification(
            "test",
            "warm",
            "",
            compiled,
            taxonomy,
            ListingClaimsConfig(version="none", claims=[]),
            "test",
            "test",
            "review",
        )
        assert result.primary_label_codes == []


@pytest.mark.parametrize(
    "subject,text",
    [
        ("CUSTOMER", "I mistakenly thought the button meant heating."),
        ("ORDER", "Only one glove arrived instead of two."),
        ("DELIVERY", "The courier delivered to the wrong address."),
        ("SERVICE", "Support declined my request."),
        ("PRODUCT", "The glove did not keep me warm."),
    ],
)
def test_responsibility_subject_survives_fact_compilation(fact_taxonomy, subject, text):
    fact = make_fact(
        subject=subject,
        sentiment="NEGATIVE",
        opinion=text,
        evidence_spans=[{"text": text}],
    )
    result = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["COLD"])]),
        comment=text,
        taxonomy=fact_taxonomy,
        allowed={"a": ["COLD"]},
    )
    assert result.extracted_facts[0].subject == subject
    assert result.semantic_units[0].subject == subject
    assert result.extracted_facts[0].actor_ref == "REVIEWER"


def test_subject_instruction_distinguishes_order_delivery_and_misunderstanding(
    fact_taxonomy,
):
    from return_semantics.fact_pipeline import extraction_messages

    instruction = extraction_messages("review", fact_taxonomy)[0]["content"]
    for rule in (
        "误认自身购买对象、功能属于CUSTOMER",
        "少收到一只）属于ORDER",
        "送错地址属于DELIVERY",
        "客服处理属于SERVICE",
        "使用表现属于PRODUCT",
        "仅描述不加热不等于买家误认",
    ):
        assert rule in instruction
