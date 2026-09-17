import json
from types import SimpleNamespace

import pytest

from return_semantics.capabilities import (
    CapabilityRegistry,
    CategoryCapability,
    ModelPolicy,
)
from return_semantics.fact_pipeline import (
    FactDecisions,
    FactMappings,
    classify_facts,
    compile_dimension_decisions,
    compile_fact_classification,
)
from return_semantics.model_client import JsonModelCallResult
from return_semantics.schemas import (
    DimensionDecision,
    ExtractedFact,
    FactMapping,
    ListingClaimsConfig,
    SemanticDisposition,
    TaxonomyConfig,
)
from return_semantics.validator import validate_classification


def _taxonomy(
    *, scope_fields: list[str] | None = None, contracts: bool = True
) -> TaxonomyConfig:
    validation_rules = {}
    if contracts:
        validation_rules["dimension_contracts"] = [
            {
                "parent_code": "TOUCHSCREEN",
                "verdict_label_codes": ["TOUCH_POSITIVE", "TOUCH_NEGATIVE"],
                "scope_fields": scope_fields
                or [
                    "experiencer_ref",
                    "product_ref",
                    "variant_ref",
                    "event_ref",
                ],
            }
        ]
    return TaxonomyConfig.model_validate(
        {
            "version": "dimension-test",
            "structure_version": 2,
            "recognition_profile": "fact_v2",
            "agent_family": "测试",
            "product_context": "手套",
            "allowed_parts": ["UNSPECIFIED", "FINGER"],
            "categories": [
                {"code": "FUNCTION", "name": "功能"},
                {
                    "code": "TOUCHSCREEN",
                    "name": "触屏灵敏性",
                    "parent_code": "FUNCTION",
                },
                {"code": "SIZE", "name": "尺码"},
                {
                    "code": "FIT",
                    "name": "总体适配",
                    "parent_code": "SIZE",
                },
            ],
            "validation_rules": validation_rules,
            "labels": [
                {
                    "code": "TOUCH_POSITIVE",
                    "name": "触屏灵敏",
                    "parent_code": "TOUCHSCREEN",
                    "allowed_sentiments": ["POSITIVE"],
                },
                {
                    "code": "TOUCH_NEGATIVE",
                    "name": "触屏不灵敏",
                    "parent_code": "TOUCHSCREEN",
                    "allowed_sentiments": ["NEGATIVE"],
                },
                {
                    "code": "FIT_ACCEPTED",
                    "name": "合身",
                    "parent_code": "FIT",
                    "allowed_sentiments": ["POSITIVE"],
                },
                {
                    "code": "FIT_TOO_BIG",
                    "name": "整体偏大",
                    "parent_code": "FIT",
                    "allowed_sentiments": ["NEGATIVE"],
                },
            ],
        }
    )


def _size_taxonomy() -> TaxonomyConfig:
    data = _taxonomy(contracts=False).model_dump(mode="json")
    data["validation_rules"]["dimension_contracts"] = [
        {
            "parent_code": "FIT",
            "verdict_label_codes": ["FIT_ACCEPTED", "FIT_TOO_BIG"],
            "scope_fields": [
                "experiencer_ref",
                "product_ref",
                "variant_ref",
                "event_ref",
            ],
        }
    ]
    return TaxonomyConfig.model_validate(data)


def _fact(identifier: str, evidence: str, sentiment: str, **updates) -> ExtractedFact:
    return ExtractedFact.model_validate(
        {
            "fact_id": identifier,
            "actor_ref": "REVIEWER",
            "source_ref": "REVIEWER",
            "experiencer_ref": "REVIEWER",
            "product_ref": "CURRENT",
            "variant_ref": "M",
            "event_ref": "E1",
            "reference_basis": "NONE",
            "fact_role": "CONCLUSION",
            "statement_type": "EXPERIENCE",
            "opinion": evidence,
            "sentiment": sentiment,
            "part": "FINGER",
            "is_primary_reason": False,
            "candidate_branch_codes": ["FUNCTION"],
            "evidence_spans": [{"text": evidence}],
            **updates,
        }
    )


def _classification(comment, taxonomy, facts, mappings):
    allowed = {
        fact.fact_id: mapping.label_codes
        for fact, mapping in zip(facts, mappings, strict=True)
    }
    return compile_fact_classification(
        facts,
        FactMappings(mappings=mappings),
        comment=comment,
        taxonomy=taxonomy,
        allowed=allowed,
    )


def _decision(parent_code, verdict, supporting, context=None, **scope_updates):
    return DimensionDecision.model_validate(
        {
            "parent_code": parent_code,
            "scope": {
                "experiencer_ref": "REVIEWER",
                "product_ref": "CURRENT",
                "variant_ref": "M",
                "event_ref": "E1",
                **scope_updates,
            },
            "verdict_label_code": verdict,
            "supporting_fact_ids": supporting,
            "context_fact_ids": context or [],
            "reason": "综合完整命题后形成唯一业务结论",
        }
    )


def test_touchscreen_context_does_not_become_opposite_terminal_label() -> None:
    comment = "Basic swipes work. Typing is less accurate than bare fingers."
    facts = [
        _fact(
            "F1",
            "Basic swipes work.",
            "POSITIVE",
            fact_role="EVIDENCE",
            operation="swipe",
        ),
        _fact(
            "F2",
            "Typing is less accurate than bare fingers.",
            "NEGATIVE",
            reference_basis="BARE_USE",
            operation="typing",
            is_primary_reason=True,
        ),
    ]
    mappings = [
        FactMapping(fact_id="F1", label_codes=["TOUCH_POSITIVE"]),
        FactMapping(fact_id="F2", label_codes=["TOUCH_NEGATIVE"]),
    ]
    taxonomy = _taxonomy()
    classification = _classification(comment, taxonomy, facts, mappings)

    result = compile_dimension_decisions(
        classification,
        FactDecisions(
            decisions=[
                _decision("TOUCHSCREEN", "TOUCH_NEGATIVE", ["F2"], context=["F1"])
            ]
        ),
        comment=comment,
        taxonomy=taxonomy,
    )

    assert [unit.label_code for unit in result.semantic_units] == ["TOUCH_NEGATIVE"]
    assert result.primary_label_codes == ["TOUCH_NEGATIVE"]
    assert result.extracted_facts == facts
    assert result.fact_mappings[0].label_codes == []
    assert result.fact_mappings[0].candidate_label_codes == ["TOUCH_POSITIVE"]
    assert result.fact_mappings[0].disposition == "EVIDENCE_ONLY"
    assert result.fact_mappings[1] == mappings[1]
    assert result.dimension_decisions[0].context_fact_ids == ["F1"]


def test_concession_keeps_accepted_size_as_only_terminal_conclusion() -> None:
    comment = "On me they look a hair too big, but I wouldn't want them any smaller."
    facts = [
        _fact(
            "F1",
            "On me they look a hair too big,",
            "NEGATIVE",
            fact_role="EVIDENCE",
            part="UNSPECIFIED",
            candidate_branch_codes=["SIZE"],
        ),
        _fact(
            "F2",
            "but I wouldn't want them any smaller.",
            "POSITIVE",
            statement_type="EVALUATION",
            part="UNSPECIFIED",
            candidate_branch_codes=["SIZE"],
        ),
    ]
    mappings = [
        FactMapping(fact_id="F1", label_codes=["FIT_TOO_BIG"]),
        FactMapping(fact_id="F2", label_codes=["FIT_ACCEPTED"]),
    ]
    taxonomy = _size_taxonomy()
    classification = _classification(comment, taxonomy, facts, mappings)

    result = compile_dimension_decisions(
        classification,
        FactDecisions(
            decisions=[_decision("FIT", "FIT_ACCEPTED", ["F2"], context=["F1"])]
        ),
        comment=comment,
        taxonomy=taxonomy,
    )

    assert [unit.label_code for unit in result.semantic_units] == ["FIT_ACCEPTED"]


def test_evidence_only_is_retained_as_auditable_ignored_fact() -> None:
    fact = _fact("F1", "Basic taps work.", "POSITIVE", fact_role="EVIDENCE")
    mapping = FactMapping(
        fact_id="F1",
        disposition=SemanticDisposition.EVIDENCE_ONLY,
        reason="仅证明基础可用",
    )

    result = _classification("Basic taps work.", _taxonomy(), [fact], [mapping])

    assert result.semantic_units == []
    assert [item.fact_id for item in result.unknown_semantics] == ["F1"]
    assert result.unknown_semantics[0].disposition == "EVIDENCE_ONLY"
    assert result.extracted_facts == [fact]
    assert result.fact_mappings == [mapping]


def test_intent_can_be_expected_abstention() -> None:
    fact = _fact(
        "F1",
        "I would buy these for a friend.",
        "NEUTRAL",
        statement_type="INTENT",
        fact_role="CONTEXT",
    )
    mapping = FactMapping(
        fact_id="F1",
        disposition=SemanticDisposition.EXPECTED_ABSTENTION,
        reason="不是商品已确认表现",
    )

    result = _classification(
        "I would buy these for a friend.", _taxonomy(), [fact], [mapping]
    )

    assert result.semantic_units == []
    assert result.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"
    assert not result.needs_review


@pytest.mark.parametrize("statement_type", ["PREDICTION", "INTENT", "NOT_TESTED"])
def test_unconfirmed_fact_cannot_support_dimension_verdict(
    statement_type: str,
) -> None:
    comment = "Typing may be inaccurate."
    fact = _fact("F1", comment, "NEGATIVE", statement_type=statement_type)
    mapping = FactMapping(fact_id="F1", label_codes=["TOUCH_NEGATIVE"])
    taxonomy = _taxonomy()
    classification = _classification(comment, taxonomy, [fact], [mapping])

    with pytest.raises(ValueError, match="支持事实必须全部候选映射"):
        compile_dimension_decisions(
            classification,
            FactDecisions(
                decisions=[_decision("TOUCHSCREEN", "TOUCH_NEGATIVE", ["F1"])]
            ),
            comment=comment,
            taxonomy=taxonomy,
        )


def test_invalid_dimension_support_is_locally_downgraded() -> None:
    comment = "Typing may be inaccurate. Swiping is responsive."
    uncertain = _fact(
        "F1",
        "Typing may be inaccurate.",
        "NEGATIVE",
        statement_type="PREDICTION",
    )
    valid = _fact("F2", "Swiping is responsive.", "POSITIVE", event_ref="E2")
    taxonomy = _taxonomy()
    classification = _classification(
        comment,
        taxonomy,
        [uncertain, valid],
        [
            FactMapping(fact_id="F1", label_codes=["TOUCH_NEGATIVE"]),
            FactMapping(fact_id="F2", label_codes=["TOUCH_POSITIVE"]),
        ],
    )

    result = compile_dimension_decisions(
        classification,
        FactDecisions(
            decisions=[
                _decision("TOUCHSCREEN", "TOUCH_NEGATIVE", ["F1"]),
                _decision(
                    "TOUCHSCREEN",
                    "TOUCH_POSITIVE",
                    ["F2"],
                    event_ref="E2",
                ),
            ]
        ),
        comment=comment,
        taxonomy=taxonomy,
        recover_invalid_decisions=True,
    )

    assert [unit.fact_id for unit in result.semantic_units] == ["F2"]
    assert result.fact_mappings[0].label_codes == []
    assert result.fact_mappings[0].candidate_label_codes == ["TOUCH_NEGATIVE"]
    assert result.fact_mappings[0].disposition == "EXPECTED_ABSTENTION"
    assert result.unknown_semantics[0].fact_id == "F1"


def test_unlabelled_evidence_does_not_remove_unique_dimension_candidate() -> None:
    comment = "Typing is inaccurate because taps are sometimes missed."
    conclusion = _fact("F1", "Typing is inaccurate", "NEGATIVE")
    evidence = _fact(
        "F2",
        "taps are sometimes missed",
        "NEGATIVE",
        fact_role="EVIDENCE",
    )
    taxonomy = _taxonomy()
    classification = _classification(
        comment,
        taxonomy,
        [conclusion, evidence],
        [
            FactMapping(fact_id="F1", label_codes=["TOUCH_NEGATIVE"]),
            FactMapping(fact_id="F2", disposition="EVIDENCE_ONLY"),
        ],
    )

    result = compile_dimension_decisions(
        classification,
        FactDecisions(decisions=[_decision("TOUCHSCREEN", "TOUCH_NEGATIVE", ["F2"])]),
        comment=comment,
        taxonomy=taxonomy,
        recover_invalid_decisions=True,
    )

    assert [unit.label_code for unit in result.semantic_units] == ["TOUCH_NEGATIVE"]
    assert result.fact_mappings[0].label_codes == ["TOUCH_NEGATIVE"]
    assert result.fact_mappings[0].disposition is None


def test_adjudicated_evidence_can_support_dimension_verdict() -> None:
    comment = "Typing is inaccurate."
    evidence = _fact(
        "F1",
        comment,
        "NEGATIVE",
        fact_role="EVIDENCE",
    )
    taxonomy = _taxonomy()
    classification = _classification(
        comment,
        taxonomy,
        [evidence],
        [
            FactMapping(
                fact_id="F1",
                label_codes=["TOUCH_NEGATIVE"],
                adjudication_action="ACCEPT",
                reason="该证据自身构成完整表现结论",
            )
        ],
    )

    result = compile_dimension_decisions(
        classification,
        FactDecisions(decisions=[_decision("TOUCHSCREEN", "TOUCH_NEGATIVE", ["F1"])]),
        comment=comment,
        taxonomy=taxonomy,
    )

    assert [unit.label_code for unit in result.semantic_units] == ["TOUCH_NEGATIVE"]
    assert result.semantic_units[0].fact_role == "EVIDENCE"


@pytest.mark.parametrize(
    "fact_updates,scope_updates",
    [
        ({"experiencer_ref": "OTHER:1", "actor_ref": "OTHER:1"}, {}),
        ({"product_ref": "CURRENT:2"}, {"product_ref": "CURRENT:1"}),
        ({"variant_ref": "S"}, {}),
        ({"event_ref": "E2"}, {}),
    ],
)
def test_cross_scope_context_cannot_hide_managed_candidate(
    fact_updates: dict, scope_updates: dict
) -> None:
    comment = "Swiping is responsive. Typing is inaccurate."
    positive = _fact("F1", "Swiping is responsive.", "POSITIVE", **scope_updates)
    negative = _fact("F2", "Typing is inaccurate.", "NEGATIVE", **fact_updates)
    mappings = [
        FactMapping(fact_id="F1", label_codes=["TOUCH_POSITIVE"]),
        FactMapping(fact_id="F2", label_codes=["TOUCH_NEGATIVE"]),
    ]
    taxonomy = _taxonomy()
    classification = _classification(comment, taxonomy, [positive, negative], mappings)

    with pytest.raises(ValueError, match="作用域与事实不一致"):
        compile_dimension_decisions(
            classification,
            FactDecisions(
                decisions=[
                    _decision(
                        "TOUCHSCREEN",
                        "TOUCH_POSITIVE",
                        ["F1"],
                        context=["F2"],
                        **scope_updates,
                    )
                ]
            ),
            comment=comment,
            taxonomy=taxonomy,
        )


def test_decision_context_resolves_only_the_referenced_unknown_fact() -> None:
    taxonomy = _taxonomy()
    comment = "Typing is inaccurate. Basic taps work. The cuff does not fit closely."
    facts = [
        _fact("F1", "Typing is inaccurate.", "NEGATIVE"),
        _fact("F8", "Basic taps work.", "POSITIVE"),
        _fact(
            "F6",
            "The cuff does not fit closely.",
            "NEGATIVE",
            part="UNSPECIFIED",
            candidate_branch_codes=["SIZE"],
        ),
    ]
    mappings = [
        FactMapping(fact_id="F1", label_codes=["TOUCH_NEGATIVE"]),
        FactMapping(
            fact_id="F8",
            reason="模型误判为标签缺口",
            disposition="TAXONOMY_GAP",
        ),
        FactMapping(
            fact_id="F6",
            reason="袖口贴合缺少标签",
            disposition="TAXONOMY_GAP",
        ),
    ]
    classification = _classification(comment, taxonomy, facts, mappings)

    result = compile_dimension_decisions(
        classification,
        FactDecisions(
            decisions=[
                _decision("TOUCHSCREEN", "TOUCH_NEGATIVE", ["F1"], context=["F8"])
            ]
        ),
        comment=comment,
        taxonomy=taxonomy,
    )

    normalized = {item.fact_id: item for item in result.fact_mappings}
    assert normalized["F8"].disposition == "EVIDENCE_ONLY"
    assert normalized["F8"].reason == "已由维度裁决作为上下文解释"
    assert normalized["F6"].disposition == "TAXONOMY_GAP"
    assert [item.fact_id for item in result.unknown_semantics] == ["F8", "F6"]
    assert result.unknown_semantics[0].disposition == "EVIDENCE_ONLY"
    assert result.needs_review


def test_explained_context_clears_false_unknown_review() -> None:
    taxonomy = _taxonomy()
    comment = "Typing is inaccurate. Basic taps work."
    facts = [
        _fact("F1", "Typing is inaccurate.", "NEGATIVE"),
        _fact("F8", "Basic taps work.", "POSITIVE"),
    ]
    mappings = [
        FactMapping(fact_id="F1", label_codes=["TOUCH_NEGATIVE"]),
        FactMapping(fact_id="F8", disposition="MAPPING_UNCERTAIN"),
    ]
    classification = _classification(comment, taxonomy, facts, mappings)
    assert classification.needs_review

    result = compile_dimension_decisions(
        classification,
        FactDecisions(
            decisions=[
                _decision("TOUCHSCREEN", "TOUCH_NEGATIVE", ["F1"], context=["F8"])
            ]
        ),
        comment=comment,
        taxonomy=taxonomy,
    )

    assert [item.fact_id for item in result.unknown_semantics] == ["F8"]
    assert result.unknown_semantics[0].disposition == "EVIDENCE_ONLY"
    assert result.fact_mappings[1].disposition == "EVIDENCE_ONLY"
    assert not result.needs_review


def test_dimension_decision_keeps_uncertainty_non_actionable() -> None:
    taxonomy = _taxonomy()
    comment = "It might be inaccurate. It is inaccurate."
    facts = [
        _fact(
            "early",
            "It might be inaccurate.",
            "NEGATIVE",
            event_ref="tentative",
            statement_type="EVALUATION",
            assertion="UNCERTAIN",
        ),
        _fact(
            "later",
            "It is inaccurate.",
            "NEGATIVE",
            event_ref="confirmed",
        ),
    ]
    mappings = [
        FactMapping(fact_id="early", label_codes=["TOUCH_NEGATIVE"]),
        FactMapping(fact_id="later", label_codes=["TOUCH_NEGATIVE"]),
    ]
    classification = _classification(comment, taxonomy, facts, mappings)

    result = compile_dimension_decisions(
        classification,
        FactDecisions(
            decisions=[
                _decision(
                    "TOUCHSCREEN",
                    "TOUCH_NEGATIVE",
                    ["later"],
                    event_ref="confirmed",
                )
            ]
        ),
        comment=comment,
        taxonomy=taxonomy,
    )

    assert [unit.label_code for unit in result.semantic_units] == ["TOUCH_NEGATIVE"]
    assert [item.fact_id for item in result.unknown_semantics] == ["early"]
    assert result.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"
    assert not result.needs_review


def test_decision_context_must_belong_to_the_same_parent_dimension() -> None:
    taxonomy = _taxonomy()
    comment = "Typing is inaccurate. The gloves fit."
    facts = [
        _fact("F1", "Typing is inaccurate.", "NEGATIVE"),
        _fact(
            "F2",
            "The gloves fit.",
            "POSITIVE",
            part="UNSPECIFIED",
            candidate_branch_codes=["SIZE"],
        ),
    ]
    mappings = [
        FactMapping(fact_id="F1", label_codes=["TOUCH_NEGATIVE"]),
        FactMapping(fact_id="F2", label_codes=["FIT_ACCEPTED"]),
    ]
    classification = _classification(comment, taxonomy, facts, mappings)

    with pytest.raises(ValueError, match="候选标签不属于配置父级"):
        compile_dimension_decisions(
            classification,
            FactDecisions(
                decisions=[
                    _decision(
                        "TOUCHSCREEN",
                        "TOUCH_NEGATIVE",
                        ["F1"],
                        context=["F2"],
                    )
                ]
            ),
            comment=comment,
            taxonomy=taxonomy,
        )


@pytest.mark.parametrize("candidate_branches", [[], ["SIZE"]])
def test_unmapped_context_must_belong_to_the_parent_branch(
    candidate_branches: list[str],
) -> None:
    taxonomy = _taxonomy()
    comment = "Typing is inaccurate. The cuff shape is unusual."
    facts = [
        _fact("F1", "Typing is inaccurate.", "NEGATIVE"),
        _fact(
            "F2",
            "The cuff shape is unusual.",
            "NEUTRAL",
            part="UNSPECIFIED",
            candidate_branch_codes=candidate_branches,
        ),
    ]
    mappings = [
        FactMapping(fact_id="F1", label_codes=["TOUCH_NEGATIVE"]),
        FactMapping(fact_id="F2", disposition="TAXONOMY_GAP"),
    ]
    classification = _classification(comment, taxonomy, facts, mappings)

    with pytest.raises(ValueError, match="事实不属于配置父级分支"):
        compile_dimension_decisions(
            classification,
            FactDecisions(
                decisions=[
                    _decision(
                        "TOUCHSCREEN",
                        "TOUCH_NEGATIVE",
                        ["F1"],
                        context=["F2"],
                    )
                ]
            ),
            comment=comment,
            taxonomy=taxonomy,
        )


def test_reference_basis_can_define_independent_scopes() -> None:
    taxonomy = _taxonomy(scope_fields=["product_ref", "variant_ref", "reference_basis"])
    comment = "It is accurate normally. It is less accurate than bare fingers."
    facts = [
        _fact("F1", "It is accurate normally.", "POSITIVE"),
        _fact(
            "F2",
            "It is less accurate than bare fingers.",
            "NEGATIVE",
            reference_basis="BARE_USE",
        ),
    ]
    mappings = [
        FactMapping(fact_id="F1", label_codes=["TOUCH_POSITIVE"]),
        FactMapping(fact_id="F2", label_codes=["TOUCH_NEGATIVE"]),
    ]
    classification = _classification(comment, taxonomy, facts, mappings)
    decisions = FactDecisions(
        decisions=[
            _decision(
                "TOUCHSCREEN",
                "TOUCH_POSITIVE",
                ["F1"],
                event_ref="UNSPECIFIED",
            ),
            _decision(
                "TOUCHSCREEN",
                "TOUCH_NEGATIVE",
                ["F2"],
                event_ref="UNSPECIFIED",
                reference_basis="BARE_USE",
            ),
        ]
    )

    result = compile_dimension_decisions(
        classification, decisions, comment=comment, taxonomy=taxonomy
    )

    assert {unit.label_code for unit in result.semantic_units} == {
        "TOUCH_POSITIVE",
        "TOUCH_NEGATIVE",
    }


def test_condition_in_contract_allows_real_mixed_conclusions() -> None:
    taxonomy = _taxonomy(
        scope_fields=[
            "experiencer_ref",
            "product_ref",
            "variant_ref",
            "event_ref",
            "condition",
        ]
    )
    comment = "It responds indoors. It misses taps in heavy rain."
    facts = [
        _fact("F1", "It responds indoors.", "POSITIVE", condition="indoors"),
        _fact(
            "F2",
            "It misses taps in heavy rain.",
            "NEGATIVE",
            condition="heavy rain",
        ),
    ]
    mappings = [
        FactMapping(fact_id="F1", label_codes=["TOUCH_POSITIVE"]),
        FactMapping(fact_id="F2", label_codes=["TOUCH_NEGATIVE"]),
    ]
    classification = _classification(comment, taxonomy, facts, mappings)
    result = compile_dimension_decisions(
        classification,
        FactDecisions(
            decisions=[
                _decision(
                    "TOUCHSCREEN",
                    "TOUCH_POSITIVE",
                    ["F1"],
                    condition="indoors",
                ),
                _decision(
                    "TOUCHSCREEN",
                    "TOUCH_NEGATIVE",
                    ["F2"],
                    condition="heavy rain",
                ),
            ]
        ),
        comment=comment,
        taxonomy=taxonomy,
    )
    validated = validate_classification(
        classification_key="test",
        comment=comment,
        reason="",
        model_result=result,
        taxonomy=taxonomy,
        claims=ListingClaimsConfig(version="none", claims=[]),
        model_name="test",
        prompt_version="test",
        analysis_context="review",
    )

    assert validated.comment_summary.status.value == "MIXED"


def test_scope_field_not_declared_by_contract_must_keep_default() -> None:
    comment = "Typing is inaccurate."
    fact = _fact("F1", comment, "NEGATIVE")
    mapping = FactMapping(fact_id="F1", label_codes=["TOUCH_NEGATIVE"])
    taxonomy = _taxonomy()
    classification = _classification(comment, taxonomy, [fact], [mapping])

    with pytest.raises(ValueError, match="未纳入契约的作用域字段必须留空"):
        compile_dimension_decisions(
            classification,
            FactDecisions(
                decisions=[
                    _decision(
                        "TOUCHSCREEN",
                        "TOUCH_NEGATIVE",
                        ["F1"],
                        operation="typing",
                    )
                ]
            ),
            comment=comment,
            taxonomy=taxonomy,
        )


def test_old_fact_and_taxonomy_without_contract_remain_compatible() -> None:
    old_fact = ExtractedFact.model_validate(
        {
            "fact_id": "F1",
            "actor_ref": "OTHER:1",
            "product_ref": "CURRENT",
            "event_ref": "E1",
            "statement_type": "EXPERIENCE",
            "opinion": "It is warm.",
            "sentiment": "POSITIVE",
            "part": "UNSPECIFIED",
            "candidate_branch_codes": ["FUNCTION"],
            "evidence_spans": [{"text": "It is warm."}],
        }
    )
    taxonomy = _taxonomy(contracts=False)
    mapping = FactMapping(fact_id="F1", label_codes=["TOUCH_POSITIVE"])
    result = _classification("It is warm.", taxonomy, [old_fact], [mapping])
    unchanged = compile_dimension_decisions(
        result,
        FactDecisions(decisions=[]),
        comment="It is warm.",
        taxonomy=taxonomy,
    )

    assert old_fact.source_ref == "OTHER:1"
    assert old_fact.experiencer_ref == "OTHER:1"
    assert old_fact.variant_ref == "UNSPECIFIED"
    assert unchanged == result


def test_contract_rejects_unknown_parent_and_overlap() -> None:
    data = _taxonomy().model_dump(mode="json")
    data["validation_rules"]["dimension_contracts"][0]["parent_code"] = "MISSING"
    with pytest.raises(ValueError, match="维度裁决契约引用了未知分类"):
        TaxonomyConfig.model_validate(data)

    data = _taxonomy().model_dump(mode="json")
    data["validation_rules"]["dimension_contracts"].append(
        {
            "parent_code": "FUNCTION",
            "verdict_label_codes": ["TOUCH_POSITIVE"],
            "scope_fields": ["product_ref"],
        }
    )
    with pytest.raises(ValueError, match="不能重叠管理"):
        TaxonomyConfig.model_validate(data)


def test_combined_taxonomy_rebases_dimension_contract() -> None:
    capability = CategoryCapability(
        key="gloves",
        agent_family="测试",
        logic_version="test",
        model_policy=ModelPolicy(
            version="test", first_pass_role="primary", review_role=None
        ),
        variants=(),
        taxonomy=_taxonomy(),
    )

    combined = CapabilityRegistry("test", (capability,)).combined_taxonomy()
    contract = combined.validation_rules.dimension_contracts[0]

    assert contract.parent_code == "gloves::TOUCHSCREEN"
    assert contract.verdict_label_codes == [
        "TOUCH_POSITIVE",
        "TOUCH_NEGATIVE",
    ]


class _FakeJsonClient:
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
                                current[fact["fact_id"]]["label_codes"][0]
                                if current[fact["fact_id"]]["label_codes"]
                                else None
                            ),
                            "action": (
                                "ACCEPT"
                                if current[fact["fact_id"]]["label_codes"]
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


def test_fact_pipeline_skips_unique_dimension_candidate() -> None:
    fact = _fact("F1", "Typing is accurate.", "POSITIVE")
    client = _FakeJsonClient(
        [
            {"facts": [fact.model_dump(mode="json")]},
            {"mappings": [{"fact_id": "F1", "label_codes": ["TOUCH_POSITIVE"]}]},
        ]
    )

    result = classify_facts(
        comment="Typing is accurate.",
        taxonomy=_taxonomy(),
        client=client,
        model_name="test",
        reasoning_effort="low",
    )

    assert result.metrics["fact_model_calls"] == 2
    assert result.metrics["dimension_decision_calls"] == 0
    assert result.metrics["dimension_decision_skips"] == 1
    assert [unit.label_code for unit in result.classification.semantic_units] == [
        "TOUCH_POSITIVE"
    ]


def test_fact_pipeline_calls_decision_for_qualifying_context() -> None:
    facts = [
        _fact("F1", "Typing is inaccurate.", "NEGATIVE"),
        _fact(
            "F2",
            "Accuracy changes under wet conditions.",
            "NEGATIVE",
            fact_role="CONTEXT",
        ),
    ]
    client = _FakeJsonClient(
        [
            {"facts": [fact.model_dump(mode="json") for fact in facts]},
            {
                "mappings": [
                    {"fact_id": "F1", "label_codes": ["TOUCH_NEGATIVE"]},
                    {
                        "fact_id": "F2",
                        "relation_type": "QUALIFIES",
                        "related_fact_ids": ["F1"],
                    },
                ]
            },
            {
                "decisions": [
                    _decision(
                        "TOUCHSCREEN",
                        "TOUCH_NEGATIVE",
                        ["F1"],
                        ["F2"],
                    ).model_dump(mode="json")
                ]
            },
        ]
    )

    result = classify_facts(
        comment="Typing is inaccurate. Accuracy changes under wet conditions.",
        taxonomy=_taxonomy(),
        client=client,
        model_name="test",
        reasoning_effort="low",
    )

    assert result.metrics["dimension_decision_calls"] == 1
    assert result.metrics["dimension_decision_skips"] == 0
    assert result.classification.dimension_decisions[0].context_fact_ids == ["F2"]


def test_fact_pipeline_calls_decision_stage_and_accumulates_usage() -> None:
    facts = [
        _fact("F1", "Typing works.", "POSITIVE"),
        _fact("F2", "Typing is inaccurate.", "NEGATIVE"),
    ]
    client = _FakeJsonClient(
        [
            {"facts": [fact.model_dump(mode="json") for fact in facts]},
            {
                "mappings": [
                    {"fact_id": "F1", "label_codes": ["TOUCH_POSITIVE"]},
                    {"fact_id": "F2", "label_codes": ["TOUCH_NEGATIVE"]},
                ]
            },
            {
                "decisions": [
                    _decision(
                        "TOUCHSCREEN",
                        "TOUCH_NEGATIVE",
                        ["F2"],
                        ["F1"],
                    ).model_dump(mode="json")
                ]
            },
        ]
    )

    result = classify_facts(
        comment="Typing works. Typing is inaccurate.",
        taxonomy=_taxonomy(),
        client=client,
        model_name="test",
        reasoning_effort="low",
    )

    assert result.metrics["fact_model_calls"] == 3
    assert result.metrics["dimension_decision_calls"] == 1
    assert result.usage["total_tokens"] == 15
    assert [unit.label_code for unit in result.classification.semantic_units] == [
        "TOUCH_NEGATIVE"
    ]
    instruction = client.messages[2][0]["content"]
    assert "维度契约" in instruction
    assert "必须属于同一contract管理的可比较业务维度" in instruction
    assert "不能仅因共享更上层分类" in instruction
