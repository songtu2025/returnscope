from return_semantics.schemas import ModelClassification
from return_semantics.validator import validate_classification


def test_unknown_semantic_reason_is_exposed_for_review(taxonomy, claims) -> None:
    model_result = ModelClassification.model_validate(
        {
            "semantic_units": [],
            "unknown_semantics": [
                {
                    "opinion": "材料偏好不明确",
                    "evidence": "didn't like the materials",
                    "reason": "当前标签没有普通材料偏好",
                }
            ],
            "primary_label_codes": [],
            "needs_review": False,
            "review_reasons": [],
        }
    )

    result = validate_classification(
        classification_key="APPAREL_STYLE\x1fmaterial",
        comment="didn't like the materials",
        reason="APPAREL_STYLE",
        model_result=model_result,
        taxonomy=taxonomy,
        claims=claims,
        model_name="test-model",
        prompt_version="test-prompt",
    )

    assert result.status.value == "UNKNOWN_SEMANTIC"
    assert result.review_reasons == ["未知语义: 当前标签没有普通材料偏好"]
