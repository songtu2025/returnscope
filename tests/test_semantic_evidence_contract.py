import pytest

from return_semantics.fact_pipeline import (
    FactMappings,
    compile_fact_classification,
    extraction_messages,
)
from return_semantics.schemas import (
    ExtractedFact,
    FactMapping,
    SemanticUnit,
    TaxonomyConfig,
)


@pytest.fixture
def taxonomy() -> TaxonomyConfig:
    return TaxonomyConfig.model_validate(
        {
            "version": "test",
            "recognition_profile": "fact_v2",
            "agent_family": "测试",
            "product_context": "测试商品",
            "labels": [
                {
                    "code": "PERFORMANCE_POSITIVE",
                    "name": "性能良好",
                    "group": "功能",
                    "allowed_sentiments": ["POSITIVE"],
                },
                {
                    "code": "DAMAGE_NEGATIVE",
                    "name": "破损",
                    "group": "质量",
                    "allowed_sentiments": ["NEGATIVE"],
                },
            ],
        }
    )


def make_fact(**updates: object) -> ExtractedFact:
    return ExtractedFact.model_validate(
        {
            "fact_id": "F1",
            "actor_ref": "REVIEWER",
            "product_ref": "CURRENT",
            "event_ref": "EVENT:1",
            "statement_type": "EXPERIENCE",
            "opinion": "当前商品实际表现良好",
            "sentiment": "POSITIVE",
            "part": "UNSPECIFIED",
            "operation": "实际使用",
            "condition": "日常场景",
            "candidate_branch_codes": ["功能"],
            "evidence_spans": [{"text": "It worked during normal use."}],
            **updates,
        }
    )


def compile_fact(
    fact: ExtractedFact,
    taxonomy: TaxonomyConfig,
    label_code: str,
    *,
    reason: str = "实际体验直接符合标签定义",
):
    return compile_fact_classification(
        [fact],
        FactMappings(
            mappings=[
                FactMapping(
                    fact_id=fact.fact_id,
                    label_codes=[label_code],
                    reason=reason,
                )
            ]
        ),
        comment=fact.evidence_spans[0].text,
        taxonomy=taxonomy,
        allowed={fact.fact_id: [label_code]},
    )


@pytest.mark.parametrize("statement_type", ["PRODUCT_CLAIM", "APPEARANCE_INFERENCE"])
def test_unverified_performance_sources_cannot_form_terminal_labels(
    taxonomy: TaxonomyConfig,
    statement_type: str,
) -> None:
    fact = make_fact(statement_type=statement_type)

    result = compile_fact(fact, taxonomy, "PERFORMANCE_POSITIVE")

    assert result.semantic_units == []
    assert result.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"
    assert not result.needs_review


def test_customer_caused_product_state_is_not_intrinsic_defect(
    taxonomy: TaxonomyConfig,
) -> None:
    fact = make_fact(
        opinion="商品因使用者主动改造而破损",
        sentiment="NEGATIVE",
        causal_attribution="CUSTOMER_ACTION",
        causal_attribution_reason="破损由使用者主动改造直接造成",
        candidate_branch_codes=["质量"],
    )

    result = compile_fact(fact, taxonomy, "DAMAGE_NEGATIVE")

    assert result.semantic_units == []
    ignored = result.unknown_semantics[0]
    assert ignored.disposition == "EXPECTED_ABSTENTION"
    assert ignored.causal_attribution == "CUSTOMER_ACTION"
    assert ignored.causal_attribution_reason == "破损由使用者主动改造直接造成"


def test_terminal_label_keeps_reviewable_fact_contract(
    taxonomy: TaxonomyConfig,
) -> None:
    fact = make_fact(
        causal_attribution="NORMAL_USE",
        causal_attribution_reason="表现来自正常使用",
    )

    result = compile_fact(fact, taxonomy, "PERFORMANCE_POSITIVE")

    unit = result.semantic_units[0]
    assert unit.opinion == "当前商品实际表现良好"
    assert unit.evidence == "It worked during normal use."
    assert unit.product_ref == "CURRENT"
    assert unit.part == "UNSPECIFIED"
    assert unit.operation == "实际使用"
    assert unit.condition == "日常场景"
    assert unit.assertion == "AFFIRMED"
    assert unit.fact_role == "CONCLUSION"
    assert unit.causal_attribution == "NORMAL_USE"
    assert unit.causal_attribution_reason == "表现来自正常使用"
    assert unit.decision_reason == "实际体验直接符合标签定义"


def test_extraction_contract_keeps_current_product_when_used_with_another_item(
    taxonomy: TaxonomyConfig,
) -> None:
    system_prompt = extraction_messages("comment", taxonomy)[0]["content"]

    assert "当前商品作为内衬、配件或与另一商品搭配使用时仍是CURRENT" in system_prompt
    assert (
        "商品宣称、外观推测、未来预测与明确未测试都不能写成已经验证的功能表现"
        in system_prompt
    )
    assert "不能把用户明确造成的结果写成商品固有缺陷" in system_prompt


def test_old_semantic_unit_gets_safe_contract_defaults() -> None:
    unit = SemanticUnit.model_validate(
        {
            "subject": "PRODUCT",
            "label_code": "LEGACY",
            "opinion": "旧结果",
            "sentiment": "POSITIVE",
            "assertion": "AFFIRMED",
            "part": "UNSPECIFIED",
            "evidence": "legacy evidence",
            "implicit": False,
        }
    )

    assert unit.fact_role == "CONCLUSION"
    assert unit.causal_attribution == "UNKNOWN"
    assert unit.causal_attribution_reason == ""
    assert unit.decision_reason == ""
    assert unit.context_fact_ids == []


def test_explicit_causal_attribution_requires_reason() -> None:
    with pytest.raises(ValueError, match="因果归属与因果说明必须同时填写"):
        make_fact(causal_attribution="CUSTOMER_ACTION")
