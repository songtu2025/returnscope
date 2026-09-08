from copy import deepcopy
from pathlib import Path

import pytest
from openpyxl import Workbook
from pydantic import ValidationError

from return_semantics.prompt import (
    build_messages,
    recognition_fingerprint,
    validation_contract_matches,
)
from return_semantics.review import should_run_secondary
from return_semantics.schemas import (
    LabelDefinition,
    ListingClaimsConfig,
    ModelClassification,
    SemanticUnit,
)
from return_semantics.semantic_guardrails import normalize_semantic_unit
from return_semantics.taxonomy import load_taxonomy
from return_semantics.validator import validate_classification
from web_backend.classification_standard_validation_service import (
    ClassificationStandardValidationService,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def eyewear():
    return load_taxonomy(ROOT / "config/taxonomy_eyewear.json")


def messages(taxonomy):
    return build_messages(
        "The product is light.",
        taxonomy,
        ListingClaimsConfig(version="none", claims=[]),
        analysis_context="review",
    )


def test_profiles_remove_aliases_without_changing_comment(eyewear):
    eyewear.labels[0].keywords = ["UNIQUE_SEARCH_ALIAS"]
    semantic = messages(eyewear)
    legacy = messages(eyewear.model_copy(update={"recognition_profile": "legacy_v3"}))
    keyword_free = messages(
        eyewear.model_copy(update={"recognition_profile": "keyword_free_v1"})
    )
    assert "UNIQUE_SEARCH_ALIAS" in legacy[0]["content"]
    assert "UNIQUE_SEARCH_ALIAS" not in semantic[0]["content"]
    assert "UNIQUE_SEARCH_ALIAS" not in keyword_free[0]["content"]
    assert semantic[1] == legacy[1] == keyword_free[1]
    assert "label_code 必须是非空" in semantic[0]["content"]


def test_alias_change_leaves_semantic_prompt_and_fingerprint_unchanged(eyewear):
    before = messages(eyewear)
    signature = recognition_fingerprint(eyewear)
    eyewear.labels[0].keywords.append("another alias")
    assert messages(eyewear) == before
    assert recognition_fingerprint(eyewear) == signature
    eyewear.labels[0].exclusions.append("仅描述小配件不代表整体偏小。")
    assert recognition_fingerprint(eyewear) != signature


def test_examples_validate_direction_and_roundtrip(eyewear):
    data = eyewear.labels[0].model_dump(mode="json")
    data["examples"] = [
        {
            "text": "Too small",
            "applies": True,
            "sentiment": "NEGATIVE",
            "explanation": "明确偏小",
        }
    ]
    assert (
        LabelDefinition.model_validate(data).model_dump(mode="json")["examples"]
        == data["examples"]
    )
    data["examples"][0]["sentiment"] = "POSITIVE"
    with pytest.raises(ValidationError):
        LabelDefinition.model_validate(data)
    data["examples"][0].update(applies=False, sentiment=None)
    assert not LabelDefinition.model_validate(data).examples[0].applies


def test_legacy_still_uses_cues_and_semantic_uses_explicit_boundary(eyewear):
    unit = SemanticUnit(
        subject="PRODUCT",
        label_code="EYEWEAR_TOO_HEAVY_U1",
        opinion="佩戴重量负担",
        sentiment="NEGATIVE",
        assertion="AFFIRMED",
        part="UNSPECIFIED",
        evidence="Feels like a brick on my face",
        implicit=False,
    )
    legacy = eyewear.model_copy(update={"recognition_profile": "legacy_v3"})
    assert normalize_semantic_unit(unit, legacy)[0] is None
    assert normalize_semantic_unit(unit, eyewear)[0] == unit
    assert "不能从压鼻" in messages(eyewear)[0]["content"]
    # 未迁移的规则继续保留词面检查，不能全局跳过。
    eyewear.validation_rules.evidence_requirements[0].semantic_requirement = ""
    assert normalize_semantic_unit(unit, eyewear)[0] is None


def test_publication_requires_matching_semantic_contract(eyewear):
    snapshot = {"taxonomy": eyewear.model_dump(mode="json")}
    source = {
        "comparison_type": "standard_version",
        "recognition_contract": {
            "candidate": {"fingerprint": recognition_fingerprint(eyewear)}
        },
    }
    assert validation_contract_matches(snapshot, source)
    assert not validation_contract_matches(snapshot, {})
    for mode in ("keyword_ab", "semantic_ab"):
        assert not validation_contract_matches(
            snapshot, {**source, "comparison_type": mode}
        )
    snapshot["taxonomy"]["labels"][0]["exclusions"].append("新的判定边界")
    assert not validation_contract_matches(snapshot, source)


def test_reference_sheet_parses_and_excludes_ambiguous_samples(eyewear):
    workbook = Workbook()
    sheet = workbook.create_sheet("人工参考答案")
    sheet.append(["评论编号", "标签编码", "评价方向", "部位", "证据", "存在歧义"])
    code = eyewear.labels[0].code
    sheet.append(["one", code, "负向", "UNSPECIFIED", "too small", ""])
    sheet.append(["two", "无标签", "", "", "", "是"])
    references = ClassificationStandardValidationService._read_references(
        workbook, eyewear.model_dump(mode="json")
    )
    actual = {
        "semantic_units": deepcopy(references["one"]["units"]),
        "status": "AUTO_APPROVED",
    }
    items = [
        {"reference": references["one"], "baseline": actual, "draft": actual},
        {"reference": references["two"], "baseline": {}, "draft": {}},
    ]
    scores = ClassificationStandardValidationService._evaluate_references(items)
    assert scores["sample_count"] == 1
    assert scores["ambiguous_count"] == 1
    assert scores["sides"]["draft"]["exact_label_samples"] == 1
    assert scores["sides"]["draft"]["extra_labels"] == 0
    changed = deepcopy(items)
    changed[0]["draft"]["semantic_units"][0]["sentiment"] = "POSITIVE"
    assert (
        ClassificationStandardValidationService._evaluate_references(changed)["sides"][
            "draft"
        ]["direction_errors"]
        == 1
    )


def test_semantic_boundary_preserves_evidence_and_requires_human_review(eyewear):
    comment = "Feels like a brick on my face"
    unit = SemanticUnit(
        subject="PRODUCT",
        label_code="EYEWEAR_TOO_HEAVY_U1",
        opinion="佩戴重量负担",
        sentiment="NEGATIVE",
        assertion="AFFIRMED",
        part="UNSPECIFIED",
        evidence=comment,
        implicit=False,
    )
    result = validate_classification(
        classification_key="semantic-boundary",
        comment=comment,
        reason="",
        model_result=ModelClassification(semantic_units=[unit]),
        taxonomy=eyewear,
        claims=ListingClaimsConfig(version="test", claims=[]),
        model_name="test",
        prompt_version="category-semantic-evidence-v1",
        analysis_context="review",
    )
    assert result.semantic_units == [unit]
    assert any("语义边界需人工确认" in reason for reason in result.review_reasons)
    assert result.status.value == "MANUAL_REVIEW"
    assert not should_run_secondary(result)
