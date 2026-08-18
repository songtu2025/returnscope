from return_semantics.schemas import ModelClassification
from return_semantics.validator import validate_classification


def _validate(payload, comment, reason, taxonomy, claims):
    return validate_classification(
        classification_key=f"{reason}\x1f{comment.lower()}",
        comment=comment,
        reason=reason,
        model_result=ModelClassification.model_validate(payload),
        taxonomy=taxonomy,
        claims=claims,
        model_name="test-model",
        prompt_version="test-prompt",
    )


def _payload(unit, primary):
    return {
        "semantic_units": [unit],
        "unknown_semantics": [],
        "primary_label_codes": primary,
        "needs_review": False,
        "review_reasons": [],
    }


def test_material_dislike_without_quality_cue_moves_to_unknown(
    taxonomy,
    claims,
) -> None:
    unit = {
        "subject": "PRODUCT",
        "label_code": "QUALITY_CHEAP_MATERIAL",
        "opinion": "不喜欢材料",
        "sentiment": "NEGATIVE",
        "assertion": "AFFIRMED",
        "part": "UPPER",
        "evidence": "didn't like the materials",
        "implicit": False,
        "claim_relation": "NONE",
        "claim_id": None,
    }
    result = _validate(
        _payload(unit, ["QUALITY_CHEAP_MATERIAL"]),
        "didn't like the materials",
        "DID_NOT_LIKE_FABRIC",
        taxonomy,
        claims,
    )

    assert result.status.value == "UNKNOWN_SEMANTIC"
    assert result.problem_label_codes == []
    assert result.primary_label_codes == []
    assert result.unknown_semantics[0].evidence == "didn't like the materials"


def test_thin_without_protection_context_clears_claim(taxonomy, claims) -> None:
    unit = {
        "subject": "PRODUCT",
        "label_code": "EXPERIENCE_THIN",
        "opinion": "鞋底太薄",
        "sentiment": "NEGATIVE",
        "assertion": "AFFIRMED",
        "part": "OUTSOLE",
        "evidence": "The sole is too thin to walk.",
        "implicit": False,
        "claim_relation": "CONTRADICTS",
        "claim_id": "CLM_PROTECT_01",
    }
    result = _validate(
        _payload(unit, ["EXPERIENCE_THIN"]),
        "Not as Expected|The sole is too thin to walk.|No",
        "NOT_AS_DESCRIBED",
        taxonomy,
        claims,
    )

    assert result.status.value == "AUTO_APPROVED"
    assert result.semantic_units[0].claim_relation.value == "NONE"
    assert result.semantic_units[0].claim_id is None


def test_requested_smaller_size_is_forced_to_implicit(taxonomy, claims) -> None:
    unit = {
        "subject": "PRODUCT",
        "label_code": "FIT_TOO_LARGE",
        "opinion": "需要更小尺码",
        "sentiment": "NEGATIVE",
        "assertion": "AFFIRMED",
        "part": "WHOLE_SHOE",
        "evidence": "Need smaller size",
        "implicit": False,
        "claim_relation": "NONE",
        "claim_id": None,
    }
    result = _validate(
        _payload(unit, ["FIT_TOO_LARGE"]),
        "Need smaller size",
        "APPAREL_TOO_LARGE",
        taxonomy,
        claims,
    )

    assert result.status.value == "SECONDARY_REVIEW"
    assert result.semantic_units[0].implicit is True
