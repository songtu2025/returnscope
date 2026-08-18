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


def _unit(
    label_code="FIT_TOO_SMALL",
    evidence="Too small",
    sentiment="NEGATIVE",
    claim_relation="NONE",
    claim_id=None,
):
    return {
        "subject": "PRODUCT",
        "label_code": label_code,
        "opinion": "尺码偏小",
        "sentiment": sentiment,
        "assertion": "AFFIRMED",
        "part": "WHOLE_SHOE",
        "evidence": evidence,
        "implicit": False,
        "claim_relation": claim_relation,
        "claim_id": claim_id,
    }


def _payload(units, primary=None, unknown=None):
    return {
        "semantic_units": units,
        "unknown_semantics": unknown or [],
        "primary_label_codes": primary or [],
        "needs_review": False,
        "review_reasons": [],
    }


def test_clear_problem_is_auto_approved(taxonomy, claims) -> None:
    result = _validate(
        _payload([_unit()], ["FIT_TOO_SMALL"]),
        "Too small",
        "APPAREL_TOO_SMALL",
        taxonomy,
        claims,
    )

    assert result.status.value == "AUTO_APPROVED"
    assert result.problem_label_codes == ["FIT_TOO_SMALL"]
    assert result.primary_label_codes == ["FIT_TOO_SMALL"]


def test_missing_evidence_requires_manual_review(taxonomy, claims) -> None:
    result = _validate(
        _payload([_unit(evidence="small overall")]),
        "Too small",
        "APPAREL_TOO_SMALL",
        taxonomy,
        claims,
    )

    assert result.status.value == "MANUAL_REVIEW"
    assert result.problem_label_codes == []
    assert "证据不在原评论中" in result.review_reasons[0]


def test_amazon_reason_conflict_requires_secondary_review(
    taxonomy,
    claims,
) -> None:
    result = _validate(
        _payload([_unit()], ["FIT_TOO_SMALL"]),
        "Too small",
        "APPAREL_TOO_LARGE",
        taxonomy,
        claims,
    )

    assert result.status.value == "SECONDARY_REVIEW"
    assert "Amazon 原因与评论方向冲突" in result.review_reasons


def test_unknown_semantic_is_not_forced_into_taxonomy(taxonomy, claims) -> None:
    result = _validate(
        _payload(
            [],
            unknown=[
                {
                    "opinion": "脚趾分隔结构疼痛",
                    "evidence": "toe divider hurts",
                    "reason": "当前标签没有脚趾分隔结构",
                }
            ],
        ),
        "The toe divider hurts",
        "NOT_AS_DESCRIBED",
        taxonomy,
        claims,
    )

    assert result.status.value == "UNKNOWN_SEMANTIC"
    assert result.problem_label_codes == []


def test_invalid_claim_mapping_requires_manual_review(taxonomy, claims) -> None:
    unit = _unit(
        label_code="FUNCTION_GRIP",
        evidence="No grip",
        claim_relation="CONTRADICTS",
        claim_id="CLM_DRY_01",
    )
    result = _validate(
        _payload([unit], ["FUNCTION_GRIP"]),
        "No grip",
        "QUALITY_UNACCEPTABLE",
        taxonomy,
        claims,
    )

    assert result.status.value == "MANUAL_REVIEW"
    assert result.problem_label_codes == []
