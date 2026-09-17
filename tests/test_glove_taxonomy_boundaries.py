from pathlib import Path

from return_semantics.prompt import build_messages
from return_semantics.schemas import ListingClaimsConfig
from return_semantics.taxonomy import load_taxonomy
from web_backend.classification_standard_issues import label_field_issues

ROOT = Path(__file__).resolve().parents[1]


def _glove_labels():
    taxonomy = load_taxonomy(ROOT / "config/taxonomy_gloves.json")
    return taxonomy, {label.code: label for label in taxonomy.labels}


def test_glove_weight_and_thickness_boundaries_are_disjoint():
    taxonomy, labels = _glove_labels()
    weight = labels["GLOVE_BULK_WEIGHT_U1"]
    thickness = labels["GLOVE_THICKNESS_U1"]

    assert taxonomy.version == "gloves-unified-2026-09-12-v1-semantic3"
    assert set(taxonomy.validation_rules.boundary_required_labels) == {
        weight.code,
        thickness.code,
    }
    assert weight.name == "轻重与负担体感"
    assert set(weight.keywords) == {"heavy", "lightweight"}
    assert thickness.name == "厚薄与轮廓体感"
    assert set(thickness.keywords) == {
        "thin",
        "thick",
        "thickness",
        "slim",
        "bulky",
        "not bulky",
    }
    assert set(weight.keywords).isdisjoint(thickness.keywords)
    assert label_field_issues(taxonomy.model_dump(mode="json")) == []


def test_glove_weight_and_thickness_boundaries_reject_cross_inference():
    _, labels = _glove_labels()
    weight = labels["GLOVE_BULK_WEIGHT_U1"]
    thickness = labels["GLOVE_THICKNESS_U1"]

    assert {example.applies for example in weight.examples} == {True, False}
    assert {example.applies for example in thickness.examples} == {True, False}
    assert any("轻便不推断手套偏薄" in item for item in weight.exclusions)
    assert any("不推断轻便、保暖、保护或质量" in item for item in thickness.exclusions)


def test_glove_prompt_contains_weight_and_thickness_boundary_contract():
    taxonomy, _ = _glove_labels()
    messages = build_messages(
        "Synthetic glove feedback.",
        taxonomy,
        ListingClaimsConfig(version="none", claims=[]),
    )
    system_prompt = messages[0]["content"]

    assert "轻重与负担体感" in system_prompt
    assert "轻便不推断手套偏薄" in system_prompt
    assert "厚薄与轮廓体感" in system_prompt
    assert "不推断轻便、保暖、保护或质量" in system_prompt
    assert "分别有明确证据时可以并存，但不得相互推断" in system_prompt


def test_glove_holdout_expressions_map_to_specific_existing_labels():
    taxonomy, labels = _glove_labels()

    assert {"touchscreen works", "use my phone", "responsive"} <= set(
        labels["GLOVE_TOUCHSCREEN_U1"].keywords
    )
    assert {"easy to slip off", "pull back on"} <= set(
        labels["GLOVE_ON_OFF_EASE_U1"].keywords
    )
    assert "nicely built" in labels["GLOVE_WORKMANSHIP_U1"].keywords
    assert {"ideal for", "well suited", "everyday use"} <= set(
        labels["GLOVE_USE_SCENARIO_U1"].keywords
    )
    assert {"inexpensive", "cheapie"} <= set(labels["GLOVE_PRICE_U1"].keywords)
    assert "for the price" in labels["GLOVE_VALUE_U1"].keywords

    system_prompt = build_messages(
        "Synthetic glove feedback.",
        taxonomy,
        ListingClaimsConfig(version="none", claims=[]),
    )[0]["content"]
    for phrase in (
        "touchscreen function worked",
        "easy to slip off and pull back on",
        "without sacrificing hand mobility",
        "nicely built pair of gloves",
        "decent cheapie pair",
        "well designed for the price",
        "short outdoor chores in winter",
        "not tested them in deep winter",
    ):
        assert phrase in system_prompt


def test_glove_verified_experience_boundaries_reject_attribute_inference():
    _, labels = _glove_labels()
    warmth = labels["GLOVE_WARMTH_U1"]
    touchscreen = labels["GLOVE_TOUCHSCREEN_U1"]
    on_off = labels["GLOVE_ON_OFF_EASE_U1"]
    scenario = labels["GLOVE_USE_SCENARIO_U1"]
    price = labels["GLOVE_PRICE_U1"]
    value = labels["GLOVE_VALUE_U1"]

    assert {example.applies for example in warmth.examples} == {True, False}
    assert any("尚未在严寒环境中测试" in item for item in warmth.exclusions)
    assert {example.applies for example in touchscreen.examples} == {True, False}
    assert any("未评价实际触控结果" in item for item in touchscreen.exclusions)
    assert {example.applies for example in on_off.examples} == {True, False}
    assert any("非主动地从手上滑落" in item for item in on_off.exclusions)
    assert {example.applies for example in scenario.examples} == {True, False}
    assert any("尚未在该场景测试" in item for item in scenario.exclusions)
    assert {example.applies for example in price.examples} == {True, False}
    assert any("cheap明确修饰材料" in item for item in price.exclusions)
    assert {example.applies for example in value.examples} == {True, False}
    assert any("只评价价格高低" in item for item in value.exclusions)
