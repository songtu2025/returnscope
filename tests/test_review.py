from return_semantics.review import reconcile_secondary, should_run_secondary
from return_semantics.schemas import ValidatedClassification


def _result(
    label_code="FIT_TOO_LARGE",
    status="SECONDARY_REVIEW",
    reasons=None,
):
    return ValidatedClassification.model_validate(
        {
            "classification_key": "key",
            "semantic_units": [
                {
                    "subject": "PRODUCT",
                    "label_code": label_code,
                    "opinion": "尺码问题",
                    "sentiment": "NEGATIVE",
                    "assertion": "AFFIRMED",
                    "part": "WHOLE_SHOE",
                    "evidence": "Need smaller size",
                    "implicit": True,
                    "claim_relation": "NONE",
                    "claim_id": None,
                }
            ],
            "unknown_semantics": [],
            "problem_label_codes": [label_code],
            "positive_label_codes": [],
            "primary_label_codes": [label_code],
            "status": status,
            "review_reasons": reasons or ["存在隐含语义"],
            "model_name": "test-model",
            "prompt_version": "test-prompt",
            "taxonomy_version": "test-taxonomy",
        }
    )


def test_matching_secondary_result_is_auto_approved() -> None:
    primary = _result()
    secondary = _result()

    assert should_run_secondary(primary) is True
    reconciled = reconcile_secondary(primary, secondary)
    assert reconciled.status.value == "AUTO_APPROVED"
    assert reconciled.review_reasons == ["二次模型结果一致"]


def test_disagreeing_secondary_result_requires_manual_review() -> None:
    primary = _result()
    secondary = _result(label_code="FIT_TOO_SMALL")

    reconciled = reconcile_secondary(primary, secondary)
    assert reconciled.status.value == "MANUAL_REVIEW"
    assert "两次模型的语义结果不一致" in reconciled.review_reasons


def test_amazon_reason_conflict_is_not_sent_to_secondary() -> None:
    primary = _result(reasons=["Amazon 原因与评论方向冲突"])

    assert should_run_secondary(primary) is False
