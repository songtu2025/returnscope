import pytest
from pydantic import ValidationError

from return_semantics.fact_pipeline import FactMappings, compile_fact_classification
from return_semantics.schemas import (
    DimensionScope,
    ExtractedFact,
    FactMapping,
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
                    "code": "QUALITY_POSITIVE",
                    "name": "质量良好",
                    "group": "质量",
                    "allowed_sentiments": ["POSITIVE"],
                }
            ],
        }
    )


def make_fact(identifier: str, **updates: object) -> ExtractedFact:
    return ExtractedFact.model_validate(
        {
            "fact_id": identifier,
            "actor_ref": "REVIEWER",
            "product_ref": "CURRENT",
            "event_ref": "EVENT:1",
            "statement_type": "EVALUATION",
            "opinion": identifier,
            "sentiment": "POSITIVE",
            "part": "UNSPECIFIED",
            "evidence_spans": [{"text": identifier}],
            "candidate_branch_codes": ["质量"],
            **updates,
        }
    )


def compile_result(
    taxonomy: TaxonomyConfig,
    facts: list[ExtractedFact],
    mappings: list[FactMapping],
):
    comment = " ".join(fact.fact_id for fact in facts)
    return compile_fact_classification(
        facts,
        FactMappings(mappings=mappings),
        comment=comment,
        taxonomy=taxonomy,
        allowed={fact.fact_id: ["QUALITY_POSITIVE"] for fact in facts},
    )


@pytest.mark.parametrize("variant_ref", ["UNSPEC", "UNSPECPECIFIED", "unspecified"])
def test_variant_sentinel_must_be_exact(variant_ref: str) -> None:
    with pytest.raises(ValidationError, match="必须精确使用UNSPECIFIED"):
        make_fact("a", variant_ref=variant_ref)

    with pytest.raises(ValidationError, match="必须精确使用UNSPECIFIED"):
        DimensionScope(variant_ref=variant_ref)


def test_exact_unspecified_variant_is_valid() -> None:
    assert make_fact("a", variant_ref="UNSPECIFIED").variant_ref == "UNSPECIFIED"
    assert DimensionScope(variant_ref="UNSPECIFIED").variant_ref == "UNSPECIFIED"


@pytest.mark.parametrize(
    "relation_type,fact_role,expected_disposition",
    [
        ("COVERED_BY", "CONCLUSION", "EXPECTED_ABSTENTION"),
        ("CAUSED_BY", "CONCLUSION", "EXPECTED_ABSTENTION"),
        ("SUPPORTS", "EVIDENCE", "EVIDENCE_ONLY"),
        ("QUALIFIES", "CONTEXT", "EVIDENCE_ONLY"),
    ],
)
def test_structured_relation_controls_non_terminal_disposition(
    taxonomy: TaxonomyConfig,
    relation_type: str,
    fact_role: str,
    expected_disposition: str | None,
) -> None:
    facts = [make_fact("a"), make_fact("b", fact_role=fact_role)]
    mappings = [
        FactMapping(fact_id="a", label_codes=["QUALITY_POSITIVE"]),
        FactMapping(
            fact_id="b",
            relation_type=relation_type,
            related_fact_ids=["a"],
        ),
    ]

    result = compile_result(taxonomy, facts, mappings)

    assert [unit.fact_id for unit in result.semantic_units] == ["a"]
    if expected_disposition is None:
        assert result.unknown_semantics == []
    else:
        assert result.unknown_semantics[0].disposition == expected_disposition
    assert not result.needs_review


def test_relation_reason_text_has_no_effect(taxonomy: TaxonomyConfig) -> None:
    facts = [make_fact("a"), make_fact("b")]
    mappings = [
        FactMapping(fact_id="a", label_codes=["QUALITY_POSITIVE"]),
        FactMapping(fact_id="b", reason="已覆盖、duplicate、summary"),
    ]

    result = compile_result(taxonomy, facts, mappings)

    assert result.unknown_semantics[0].disposition == "TAXONOMY_GAP"
    assert result.needs_review


@pytest.mark.parametrize("fact_role", ["EVIDENCE", "CONTEXT"])
def test_non_conclusion_mapping_cannot_form_terminal_label(
    taxonomy: TaxonomyConfig,
    fact_role: str,
) -> None:
    fact = make_fact("a", fact_role=fact_role)

    result = compile_result(
        taxonomy,
        [fact],
        [FactMapping(fact_id="a", label_codes=["QUALITY_POSITIVE"])],
    )

    assert result.semantic_units == []
    assert [item.fact_id for item in result.unknown_semantics] == ["a"]
    assert result.unknown_semantics[0].disposition == "EVIDENCE_ONLY"
    assert not result.needs_review


@pytest.mark.parametrize(
    "mapping,fact_role,error",
    [
        (
            FactMapping(
                fact_id="b",
                relation_type="COVERED_BY",
                related_fact_ids=["missing"],
            ),
            "CONCLUSION",
            "未知事实",
        ),
        (
            FactMapping(
                fact_id="b",
                label_codes=["QUALITY_POSITIVE"],
                relation_type="SUPPORTS",
                related_fact_ids=["a"],
            ),
            "EVIDENCE",
            "不能同时生成候选标签",
        ),
    ],
)
def test_invalid_relation_is_rejected(
    taxonomy: TaxonomyConfig,
    mapping: FactMapping,
    fact_role: str,
    error: str,
) -> None:
    facts = [make_fact("a"), make_fact("b", fact_role=fact_role)]

    with pytest.raises(ValueError, match=error):
        compile_result(
            taxonomy,
            facts,
            [FactMapping(fact_id="a", label_codes=["QUALITY_POSITIVE"]), mapping],
        )


def test_relation_requires_compatible_core_scope(taxonomy: TaxonomyConfig) -> None:
    facts = [
        make_fact("a"),
        make_fact(
            "b",
            fact_role="EVIDENCE",
            actor_ref="OTHER:1",
            experiencer_ref="OTHER:1",
        ),
    ]
    mappings = [
        FactMapping(fact_id="a", label_codes=["QUALITY_POSITIVE"]),
        FactMapping(
            fact_id="b",
            relation_type="SUPPORTS",
            related_fact_ids=["a"],
        ),
    ]

    with pytest.raises(ValueError, match="作用域不相容"):
        compile_result(taxonomy, facts, mappings)


def test_same_event_relation_cannot_cross_events(taxonomy: TaxonomyConfig) -> None:
    facts = [
        make_fact("a"),
        make_fact("b", fact_role="EVIDENCE", event_ref="EVENT:2"),
    ]
    mappings = [
        FactMapping(fact_id="a", label_codes=["QUALITY_POSITIVE"]),
        FactMapping(
            fact_id="b",
            relation_type="SUPPORTS",
            related_fact_ids=["a"],
        ),
    ]

    with pytest.raises(ValueError, match="作用域不相容"):
        compile_result(taxonomy, facts, mappings)


def test_relation_requires_matching_source_role(taxonomy: TaxonomyConfig) -> None:
    facts = [make_fact("a"), make_fact("b", fact_role="CONTEXT")]
    mappings = [
        FactMapping(fact_id="a", label_codes=["QUALITY_POSITIVE"]),
        FactMapping(
            fact_id="b",
            relation_type="SUPPORTS",
            related_fact_ids=["a"],
        ),
    ]

    with pytest.raises(ValueError, match="来源角色不一致"):
        compile_result(taxonomy, facts, mappings)


def test_old_mapping_without_relation_fields_remains_valid() -> None:
    mapping = FactMapping.model_validate({"fact_id": "a", "label_codes": []})

    assert mapping.relation_type == "NONE"
    assert mapping.related_fact_ids == []


def test_self_reference_is_rejected_by_schema() -> None:
    with pytest.raises(ValueError, match="不能引用自身"):
        FactMapping(
            fact_id="a",
            relation_type="SUPPORTS",
            related_fact_ids=["a"],
        )
