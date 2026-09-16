import pytest

from return_semantics.schemas import (
    LabelDefinition,
    ModelClassification,
)
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
    subject="PRODUCT",
):
    return {
        "subject": subject,
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


def test_final_validator_suppresses_fallback_covered_by_specific_unit(
    taxonomy, claims
) -> None:
    comment = "The item performed well in the same test."
    candidate = taxonomy.model_copy(
        update={
            "validation_rules": taxonomy.validation_rules.model_copy(
                update={"fallback_label_codes": ["EXPERIENCE_WEIGHT"]}
            )
        }
    )
    fallback = _unit("EXPERIENCE_WEIGHT", comment, sentiment="POSITIVE")
    specific = _unit("FUNCTION_SAND_RESISTANCE", comment, sentiment="POSITIVE")

    result = _validate(
        _payload([fallback, specific]),
        comment,
        "UNWANTED_ITEM",
        candidate,
        claims,
    )

    assert [unit.label_code for unit in result.semantic_units] == [
        "FUNCTION_SAND_RESISTANCE"
    ]


def test_water_shoe_seam_fault_preserves_part_and_usage_evidence(taxonomy, claims):
    comment = "The heel seam opened after two uses"
    unit = _unit("QUALITY_SEAM_FAILURE", comment)
    unit.update(part="HEEL", opinion="使用两次后鞋跟接缝开线")
    result = _validate(_payload([unit]), comment, "DEFECTIVE", taxonomy, claims)
    assert result.status.value == "AUTO_APPROVED"
    assert result.problem_label_codes == ["QUALITY_SEAM_FAILURE"]
    assert result.semantic_units[0].part == "HEEL"
    assert result.semantic_units[0].evidence == comment


@pytest.mark.parametrize(
    ("code", "comment"),
    [
        ("QUALITY_COLORFAST_POSITIVE", "The color did not bleed"),
        ("FUNCTION_SAND_RESISTANCE", "The shoes kept sand out"),
        ("QUALITY_DURABLE_POSITIVE", "These shoes are durable"),
        ("EXPERIENCE_WEIGHT", "These shoes are lightweight"),
    ],
)
def test_water_shoe_praise_never_becomes_return_problem(
    taxonomy, claims, code, comment
):
    result = _validate(
        _payload([_unit(code, comment, sentiment="POSITIVE")]),
        comment,
        "UNWANTED_ITEM",
        taxonomy,
        claims,
    )
    assert result.problem_label_codes == []
    assert result.primary_label_codes == []
    assert result.positive_label_codes == [code]


def test_new_drying_label_can_reference_existing_listing_claim(taxonomy, claims):
    comment = "The shoes take days to dry"
    result = _validate(
        _payload(
            [
                _unit(
                    "FUNCTION_QUICK_DRY",
                    comment,
                    claim_relation="CONTRADICTS",
                    claim_id="CLM_DRY_01",
                )
            ]
        ),
        comment,
        "QUALITY_UNACCEPTABLE",
        taxonomy,
        claims,
    )
    assert result.status.value == "AUTO_APPROVED"
    assert result.semantic_units[0].claim_id == "CLM_DRY_01"


def test_generic_breakage_and_specific_fault_require_review(taxonomy, claims):
    comment = "The shoes fell apart when the seam opened"
    result = _validate(
        _payload(
            [
                _unit("QUALITY_FALLING_APART", "fell apart"),
                _unit("QUALITY_SEAM_FAILURE", "seam opened"),
            ]
        ),
        comment,
        "DEFECTIVE",
        taxonomy,
        claims,
    )
    assert result.status.value == "SECONDARY_REVIEW"
    assert any("相反标签" in reason for reason in result.review_reasons)


def test_service_is_a_supported_semantic_subject(taxonomy, claims) -> None:
    result = _validate(
        _payload(
            [_unit(subject="SERVICE")],
            ["FIT_TOO_SMALL"],
        ),
        "Too small",
        "APPAREL_TOO_SMALL",
        taxonomy,
        claims,
    )

    assert result.semantic_units[0].subject.value == "SERVICE"


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


def test_expected_abstention_does_not_trigger_unknown_status(taxonomy, claims) -> None:
    result = _validate(
        _payload(
            [],
            unknown=[
                {
                    "opinion": "尚未测试防水",
                    "evidence": "not tested in rain",
                    "reason": "未发生测试",
                    "disposition": "EXPECTED_ABSTENTION",
                    "statement_type": "NOT_TESTED",
                }
            ],
        ),
        "not tested in rain",
        "",
        taxonomy,
        claims,
    )

    assert result.status.value == "AUTO_APPROVED"
    assert result.comment_summary.status.value == "NO_CONFIRMED"


@pytest.mark.parametrize(
    (
        "right_condition",
        "right_actor",
        "right_event",
        "right_operation",
        "summary_status",
        "relation_type",
    ),
    [
        ("outdoors", "REVIEWER", "E1", "SWIPE", "MIXED", "MIXED"),
        ("indoors", "REVIEWER", "E2", "SWIPE", "MIXED", "MIXED"),
        ("indoors", "REVIEWER", "E1", "TYPE", "MIXED", "MIXED"),
        ("indoors", "REVIEWER", "E1", "SWIPE", "CONFLICT", "CONFLICT"),
        ("indoors", "OTHER:1", "E1", "SWIPE", "MIXED", "MULTI_ACTOR"),
    ],
)
def test_comment_summary_preserves_semantic_scope(
    taxonomy,
    claims,
    right_condition,
    right_actor,
    right_event,
    right_operation,
    summary_status,
    relation_type,
) -> None:
    code = "FIT_TOO_SMALL"
    labels = [
        label.model_copy(update={"allowed_sentiments": ["POSITIVE", "NEGATIVE"]})
        if label.code == code
        else label
        for label in taxonomy.labels
    ]
    scoped_taxonomy = taxonomy.model_copy(update={"labels": labels})
    positive = _unit(code, "Works indoors", sentiment="POSITIVE")
    positive.update(
        fact_id="F1",
        condition="indoors",
        actor_ref="REVIEWER",
        event_ref="E1",
        operation="SWIPE",
        statement_type="EXPERIENCE",
    )
    negative = _unit(code, "Fails elsewhere")
    negative.update(
        fact_id="F2",
        condition=right_condition,
        actor_ref=right_actor,
        event_ref=right_event,
        operation=right_operation,
        statement_type="EXPERIENCE",
    )

    result = _validate(
        _payload([positive, negative]),
        "Works indoors. Fails elsewhere",
        "",
        scoped_taxonomy,
        claims,
    )

    assert result.comment_summary.status.value == summary_status
    assert result.semantic_relations[0].relation_type.value == relation_type
    assert result.semantic_relations[0].fact_ids == ["F1", "F2"]


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


def test_neutral_other_group_is_a_problem_label(taxonomy, claims) -> None:
    buyer_reason = LabelDefinition(
        code="EYEWEAR_BUYER_REASON",
        name="买家自身原因/不需要",
        group="其他",
        description="买家改变需求或不再需要",
        allowed_sentiments=["NEUTRAL"],
    )
    eyewear_taxonomy = taxonomy.model_copy(
        update={"labels": [*taxonomy.labels, buyer_reason]}
    )
    unit = _unit(
        label_code="EYEWEAR_BUYER_REASON",
        evidence="No longer needed",
        sentiment="NEUTRAL",
    )

    result = _validate(
        _payload([unit]),
        "No longer needed",
        "NO_LONGER_NEEDED",
        eyewear_taxonomy,
        claims,
    )

    assert result.problem_label_codes == ["EYEWEAR_BUYER_REASON"]


def test_positive_fallback_conflict_requires_secondary_review(
    taxonomy,
    claims,
) -> None:
    specific = LabelDefinition(
        code="EYEWEAR_FIT_POSITIVE",
        name="尺码合适/贴合",
        group="正向反馈",
        description="明确表示尺寸合适",
        allowed_sentiments=["POSITIVE"],
    )
    fallback = LabelDefinition(
        code="EYEWEAR_OVERALL_POSITIVE",
        name="整体满意/推荐",
        group="正向反馈",
        description="没有具体正向信息时使用",
        allowed_sentiments=["POSITIVE"],
    )
    rules = taxonomy.validation_rules.model_copy(
        update={
            "conflicting_label_sets": [
                *taxonomy.validation_rules.conflicting_label_sets,
                [specific.code, fallback.code],
            ]
        }
    )
    eyewear_taxonomy = taxonomy.model_copy(
        update={
            "labels": [*taxonomy.labels, specific, fallback],
            "validation_rules": rules,
        }
    )
    units = [
        _unit(
            label_code=specific.code,
            evidence="Fits perfectly",
            sentiment="POSITIVE",
        ),
        _unit(
            label_code=fallback.code,
            evidence="love it",
            sentiment="POSITIVE",
        ),
    ]

    result = _validate(
        _payload(units),
        "Fits perfectly, love it",
        "",
        eyewear_taxonomy,
        claims,
    )

    assert result.status.value == "SECONDARY_REVIEW"
    assert any("评论包含相反标签" in reason for reason in result.review_reasons)
