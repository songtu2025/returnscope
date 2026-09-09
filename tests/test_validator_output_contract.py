import pytest

from return_semantics.schemas import (
    AssertionCode,
    ClaimRelation,
    LabelDefinition,
    ListingClaimsConfig,
    ModelClassification,
    SemanticUnit,
    TaxonomyConfig,
)
from return_semantics.validator import collect_output_errors, validate_classification


@pytest.fixture
def contract_taxonomy(taxonomy):
    return taxonomy.model_copy(
        update={
            "labels": [
                LabelDefinition(
                    code="TEST",
                    name="测试",
                    group="测试",
                    allowed_sentiments=["NEGATIVE", "POSITIVE"],
                    allowed_claim_ids=["C1", "C2"],
                )
            ],
        }
    )


@pytest.fixture
def contract_claims():
    return ListingClaimsConfig.model_validate(
        {
            "version": "test",
            "claims": [
                {
                    "claim_id": code,
                    "text": "测试承诺",
                    "source": "test",
                    "allowed_label_codes": ["TEST"],
                }
                for code in ["C1", "C2"]
            ],
        }
    )


@pytest.fixture
def unit():
    return SemanticUnit.model_validate(
        {
            "subject": "PRODUCT",
            "label_code": "TEST",
            "opinion": "不合适",
            "sentiment": "NEGATIVE",
            "assertion": "AFFIRMED",
            "part": "HEEL",
            "evidence": "does not fit",
            "implicit": False,
            "claim_relation": "NONE",
            "claim_id": None,
        }
    )


def _validate(model, taxonomy: TaxonomyConfig, claims: ListingClaimsConfig):
    return validate_classification(
        "key",
        "does not fit; too small",
        "",
        model,
        taxonomy,
        claims,
        "test",
        "test",
        "review",
    )


def test_exact_duplicate_is_removed_without_mutating_input(
    unit,
    contract_taxonomy,
    contract_claims,
):
    model = ModelClassification(semantic_units=[unit, unit.model_copy()])
    before = model.model_dump()
    result = _validate(model, contract_taxonomy, contract_claims)
    assert result.semantic_units == [unit]
    assert result.problem_label_codes == ["TEST"]
    assert model.model_dump() == before
    assert (
        collect_output_errors(
            model,
            "does not fit",
            contract_taxonomy,
            contract_claims,
        )
        == []
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"subject": "CUSTOMER"},
        {"part": "TOE"},
        {"opinion": "另一位使用者不合适"},
        {"evidence": "too small"},
        {"sentiment": "POSITIVE"},
        {"implicit": True},
        {"claim_relation": ClaimRelation.CONTRADICTS, "claim_id": "C1"},
    ],
)
def test_same_code_with_any_distinct_fact_is_preserved(
    unit,
    contract_taxonomy,
    contract_claims,
    changes,
):
    changed = SemanticUnit.model_validate({**unit.model_dump(), **changes})
    model = ModelClassification(semantic_units=[unit, changed])
    assert _validate(model, contract_taxonomy, contract_claims).semantic_units == [
        unit,
        changed,
    ]


def test_different_claim_ids_are_preserved(unit, contract_taxonomy, contract_claims):
    units = [
        unit.model_copy(
            update={
                "claim_relation": ClaimRelation.CONTRADICTS,
                "claim_id": claim_id,
            }
        )
        for claim_id in ["C1", "C2"]
    ]
    result = _validate(
        ModelClassification(semantic_units=units), contract_taxonomy, contract_claims
    )
    assert result.semantic_units == units


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"label_code": "NONEXISTENT"}, "未知标签: NONEXISTENT"),
        ({"sentiment": "NEUTRAL"}, "标签情感方向无效: TEST"),
        ({"evidence": "invented evidence"}, "证据不在原评论中: TEST"),
        ({"part": "SOLE"}, "部位不适用于当前品类: SOLE"),
        ({"claim_id": "C1"}, "无承诺关系却提供了承诺编号: TEST"),
        (
            {"claim_relation": ClaimRelation.CONTRADICTS, "claim_id": "UNKNOWN"},
            "承诺编号无效: UNKNOWN",
        ),
    ],
)
def test_hard_errors_remain_available_without_rewriting_original(
    unit,
    contract_taxonomy,
    contract_claims,
    changes,
    message,
):
    invalid = SemanticUnit.model_validate({**unit.model_dump(), **changes})
    model = ModelClassification(semantic_units=[invalid])
    before = model.model_dump()
    errors = collect_output_errors(
        model,
        "does not fit",
        contract_taxonomy,
        contract_claims,
    )
    assert message in errors
    result = _validate(model, contract_taxonomy, contract_claims)
    assert message in result.review_reasons
    assert result.semantic_units == []
    assert model.model_dump() == before


def test_invalid_primary_and_unknown_evidence_are_diagnosed(
    unit,
    contract_taxonomy,
    contract_claims,
):
    model = ModelClassification.model_validate(
        {
            "semantic_units": [unit.model_dump()],
            "primary_label_codes": ["MISSING"],
            "unknown_semantics": [
                {"opinion": "未知", "evidence": "invented", "reason": "待确定"}
            ],
        }
    )
    errors = collect_output_errors(
        model, "does not fit", contract_taxonomy, contract_claims
    )
    assert "未知语义证据不在原评论中" in errors
    assert "主因不属于问题标签: ['MISSING']" in errors


@pytest.mark.parametrize("assertion", ["UNCERTAIN", "NEGATED"])
def test_soft_assertion_risk_is_not_an_output_error(
    unit,
    contract_taxonomy,
    contract_claims,
    assertion,
):
    model = ModelClassification(
        semantic_units=[
            unit.model_copy(update={"assertion": AssertionCode(assertion)}),
        ]
    )
    assert (
        collect_output_errors(model, "does not fit", contract_taxonomy, contract_claims)
        == []
    )
    result = _validate(model, contract_taxonomy, contract_claims)
    assert "语义并非已确认事实: TEST" in result.review_reasons
