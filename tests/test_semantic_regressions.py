from pathlib import Path

import pytest

from return_semantics.prompt import PROMPT_VERSION, build_messages
from return_semantics.schemas import (
    ListingClaimsConfig,
    ModelClassification,
)
from return_semantics.taxonomy import load_taxonomy
from return_semantics.validator import validate_classification


def test_prompt_contains_direction_and_overreach_rules(taxonomy, claims) -> None:
    messages = build_messages("Need smaller size", taxonomy, claims)
    system_prompt = messages[0]["content"]

    assert PROMPT_VERSION == "category-semantic-v5"
    assert "不能推断材料廉价" in system_prompt
    assert "只说鞋底薄时不能关联保护承诺" in system_prompt


def test_size_preference_requires_context_before_inferring_fit(taxonomy, claims):
    candidate = taxonomy.model_copy(update={"instructions": []})
    system = build_messages("Need smaller size", candidate, claims)[0]["content"]

    assert "尺码需求或换码偏好本身不等于收到的商品不合身" in system
    assert "上下文明确描述实际偏大、偏小或其他不合身体验" in system
    assert "单纯选码需求使用允许的中性标签" in system
    assert "未覆盖时保留未知" in system
    assert "Need smaller size 表示收到的商品偏大" not in system


def test_prompt_compacts_catalog_without_claims(taxonomy) -> None:
    claims = ListingClaimsConfig(version="all-listings", claims=[])
    messages = build_messages("Too small", taxonomy, claims)
    system_prompt = messages[0]["content"]

    first = taxonomy.labels[0]
    assert (
        f"FIT_TOO_LARGE|{first.group} → {first.name}|整体尺码明显偏大|NEGATIVE|large,big"
        in system_prompt
    )
    assert "Listing 承诺（编号|文本|允许标签，仅用于关系判断）：\n无" in system_prompt
    assert '"code":' not in system_prompt
    assert '"claim_id": null' in system_prompt
    assert len(system_prompt) < 12000


def test_water_shoe_prompt_covers_framework_boundaries(taxonomy):
    prompt = build_messages(
        "The seam opened after two uses",
        taxonomy,
        ListingClaimsConfig(version="none", claims=[]),
    )[0]["content"]
    for boundary in (
        "设计排水孔不能判为质量破洞",
        "干燥速度与排水表现分别判断",
        "不能相互推导",
        "在 opinion 和 evidence 中保留尺码原文",
        "儿童凉鞋不自动具有水鞋功能",
        "不因表格分组推断责任方",
    ):
        assert boundary in prompt


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


@pytest.mark.parametrize(
    ("code", "comment", "sentiment", "part", "expected"),
    [
        (
            "EYEWEAR_TOO_HEAVY_U1",
            "The nose pads dig into my nose.",
            "NEGATIVE",
            "NOSE_PAD",
            "UNKNOWN_SEMANTIC",
        ),
        (
            "EYEWEAR_TOO_HEAVY_U1",
            "These glasses are too heavy.",
            "NEGATIVE",
            "FRAME",
            "AUTO_APPROVED",
        ),
        (
            "EYEWEAR_REASON_UNSPECIFIED_U1",
            "No comment.",
            "NEGATIVE",
            "UNSPECIFIED",
            "UNKNOWN_SEMANTIC",
        ),
        (
            "EYEWEAR_LENS_BREAKAGE_U1",
            "The right lens cracked after two days.",
            "NEGATIVE",
            "LENS",
            "AUTO_APPROVED",
        ),
        (
            "EYEWEAR_FOGGING_PERFORMANCE_U1",
            "The lenses never fog up.",
            "POSITIVE",
            "LENS",
            "SECONDARY_REVIEW",
        ),
    ],
)
def test_eyewear_evidence_and_direction(
    code,
    comment,
    sentiment,
    part,
    expected,
) -> None:
    taxonomy = load_taxonomy(
        Path(__file__).resolve().parents[1] / "config/taxonomy_eyewear.json"
    )
    taxonomy = taxonomy.model_copy(update={"recognition_profile": "legacy_v3"})
    model_result = ModelClassification.model_validate(
        {
            "semantic_units": [
                {
                    "subject": "PRODUCT",
                    "label_code": code,
                    "opinion": "保留评论明示的产品体验",
                    "sentiment": sentiment,
                    "assertion": "AFFIRMED",
                    "part": part,
                    "evidence": comment,
                    "implicit": False,
                }
            ],
            "primary_label_codes": [code] if sentiment == "NEGATIVE" else [],
        }
    )
    result = validate_classification(
        classification_key="eyewear-regression",
        comment=comment,
        reason="",
        model_result=model_result,
        taxonomy=taxonomy,
        claims=ListingClaimsConfig(version="none", claims=[]),
        model_name="test",
        prompt_version=PROMPT_VERSION,
    )
    assert result.status.value == expected
    if expected == "UNKNOWN_SEMANTIC":
        assert result.problem_label_codes == []
        assert result.primary_label_codes == []
    elif sentiment == "POSITIVE":
        assert result.positive_label_codes == [code]
        assert result.problem_label_codes == []


def test_eyewear_prompt_preserves_age_and_review_boundaries() -> None:
    taxonomy = load_taxonomy(
        Path(__file__).resolve().parents[1] / "config/taxonomy_eyewear.json"
    )
    prompt = build_messages(
        "Too small for my 10-year-old.",
        taxonomy,
        ListingClaimsConfig(version="none", claims=[]),
    )[0]["content"]
    for boundary in (
        "不是具体Listing的年龄承诺",
        "包装打开不能推断二手",
        "必须设置needs_review=true",
        "镜片破裂、镜片脱落",
        "不能从遮光或眩光体验推断UV防护不合格",
    ):
        assert boundary in prompt
    assert (
        taxonomy.validation_rules.conflicting_label_sets.count(
            sorted(["EYEWEAR_QUALITY_GENERAL_U1", "EYEWEAR_LENS_BREAKAGE_U1"])
        )
        == 1
    )
