from return_semantics.prompt import PROMPT_VERSION, build_messages
from return_semantics.schemas import (
    ListingClaimsConfig,
    ModelClassification,
)
from return_semantics.validator import validate_classification


def test_prompt_contains_direction_and_overreach_rules(taxonomy, claims) -> None:
    messages = build_messages("Need smaller size", taxonomy, claims)
    system_prompt = messages[0]["content"]

    assert PROMPT_VERSION == "category-semantic-v1"
    assert "Need smaller size 表示收到的商品偏大" in system_prompt
    assert "不能推断材料廉价" in system_prompt
    assert "只说鞋底薄时不能关联保护承诺" in system_prompt


def test_prompt_compacts_catalog_without_claims(taxonomy) -> None:
    claims = ListingClaimsConfig(version="all-listings", claims=[])
    messages = build_messages("Too small", taxonomy, claims)
    system_prompt = messages[0]["content"]

    assert "FIT_TOO_LARGE|整体尺码明显偏大|NEGATIVE" in system_prompt
    assert "Listing 承诺（编号|文本|允许标签，仅用于关系判断）：\n无" in system_prompt
    assert '"code":' not in system_prompt
    assert '"claim_id": null' in system_prompt
    assert len(system_prompt) < 4200


def test_neutral_buyer_reason_is_kept_as_return_cause(taxonomy, claims) -> None:
    model_result = ModelClassification.model_validate(
        {
            "semantic_units": [
                {
                    "subject": "CUSTOMER",
                    "label_code": "OTHER_BUYER_CHANGED_MIND",
                    "opinion": "买家需求改变",
                    "sentiment": "NEUTRAL",
                    "assertion": "AFFIRMED",
                    "part": "UNSPECIFIED",
                    "evidence": "My needs changed",
                    "implicit": False,
                    "claim_relation": "NONE",
                    "claim_id": None,
                }
            ],
            "unknown_semantics": [],
            "primary_label_codes": [],
            "needs_review": False,
            "review_reasons": [],
        }
    )

    result = validate_classification(
        classification_key="UNWANTED_ITEM\x1fchanged mind",
        comment="Changed Mind|My needs changed",
        reason="UNWANTED_ITEM",
        model_result=model_result,
        taxonomy=taxonomy,
        claims=claims,
        model_name="test-model",
        prompt_version=PROMPT_VERSION,
    )

    assert result.status.value == "AUTO_APPROVED"
    assert result.problem_label_codes == ["OTHER_BUYER_CHANGED_MIND"]
    assert result.primary_label_codes == ["OTHER_BUYER_CHANGED_MIND"]
