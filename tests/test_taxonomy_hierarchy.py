from pathlib import Path

import pytest
from pydantic import ValidationError

from return_semantics.capabilities import (
    CapabilityRegistry,
    CategoryCapability,
    ModelPolicy,
)
from return_semantics.prompt import build_messages, recognition_fingerprint
from return_semantics.schemas import (
    ListingClaimsConfig,
    ModelClassification,
    TaxonomyConfig,
)
from return_semantics.taxonomy import adapt_claims_to_taxonomy, load_taxonomy
from return_semantics.taxonomy_hierarchy import (
    descendant_label_codes,
    label_path,
    label_path_codes,
)
from return_semantics.validator import validate_classification


@pytest.fixture
def tree_payload():
    return {
        "version": "手套-v2",
        "structure_version": 2,
        "recognition_profile": "semantic_v1",
        "agent_family": "gloves",
        "product_context": "手套",
        "categories": [
            {"code": "FUNCTION", "name": "功能"},
            {"code": "WARMTH", "name": "保暖性", "parent_code": "FUNCTION"},
            {"code": "QUALITY", "name": "质量"},
        ],
        "labels": [
            {
                "code": "COLD",
                "name": "不保暖",
                "parent_code": "WARMTH",
                "description": "明确表达保暖不足",
                "allowed_sentiments": ["NEGATIVE"],
            },
            {
                "code": "FAULT",
                "name": "不保暖",
                "parent_code": "QUALITY",
                "description": "测试同名分支",
                "allowed_sentiments": ["NEGATIVE"],
            },
        ],
        "validation_rules": {"allowed_groups": ["旧分组"]},
    }


def test_paths_survive_roundtrip_and_derive_groups(tree_payload):
    taxonomy = TaxonomyConfig.model_validate(tree_payload)
    taxonomy = TaxonomyConfig.model_validate(taxonomy.model_dump(mode="json"))
    assert label_path(taxonomy, "COLD") == ["功能", "保暖性", "不保暖"]
    assert label_path(taxonomy, "FAULT") == ["质量", "不保暖"]
    assert label_path(taxonomy, "WARMTH") == ["功能", "保暖性"]
    assert label_path_codes(taxonomy, "COLD") == ["FUNCTION", "WARMTH", "COLD"]
    assert descendant_label_codes(taxonomy, "FUNCTION") == ["COLD"]
    assert taxonomy.labels[0].group == "功能"
    assert label_path(taxonomy, "missing") == []


@pytest.mark.parametrize(
    "defect", ["cycle", "missing", "duplicate", "no_parent", "label_parent"]
)
def test_invalid_trees_are_rejected(tree_payload, defect):
    if defect == "cycle":
        tree_payload["categories"][0]["parent_code"] = "WARMTH"
    elif defect == "missing":
        tree_payload["categories"][0]["parent_code"] = "missing"
    elif defect == "duplicate":
        tree_payload["labels"][0]["code"] = "FUNCTION"
    elif defect == "no_parent":
        tree_payload["labels"][0]["parent_code"] = None
    else:
        tree_payload["labels"][0]["parent_code"] = "FAULT"
    with pytest.raises(ValidationError):
        TaxonomyConfig.model_validate(tree_payload)


def test_path_prompt_invalidates_old_fingerprint_but_roundtrip_is_stable():
    taxonomy = load_taxonomy(Path("config/taxonomy_eyewear.json"))
    signature = recognition_fingerprint(taxonomy)
    taxonomy = TaxonomyConfig.model_validate_json(taxonomy.model_dump_json())
    assert recognition_fingerprint(taxonomy) == signature
    assert (
        recognition_fingerprint(taxonomy)
        != "c4774ecf3651d1d25e4c0c7373ff1988d2cb973c5120c57900d24c05c06ced5c"
    )


def test_four_level_branch_preserves_all_ancestors(tree_payload):
    tree_payload["categories"].append(
        {"code": "WINTER", "name": "冬季体验", "parent_code": "WARMTH"}
    )
    tree_payload["labels"][0]["parent_code"] = "WINTER"
    taxonomy = TaxonomyConfig.model_validate(tree_payload)
    assert label_path(taxonomy, "COLD") == ["功能", "保暖性", "冬季体验", "不保暖"]
    assert descendant_label_codes(taxonomy, "WARMTH") == ["COLD"]


@pytest.mark.parametrize("profile", ["legacy_v3", "keyword_free_v1", "semantic_v1"])
def test_prompt_contains_path_and_path_changes_invalidate_cache(tree_payload, profile):
    tree_payload["recognition_profile"] = profile
    taxonomy = TaxonomyConfig.model_validate(tree_payload)
    prompt = build_messages(
        "不保暖", taxonomy, ListingClaimsConfig(version="v1", claims=[])
    )
    assert '"完整路径": ["功能", "保暖性", "不保暖"]' in prompt[0]["content"]
    assert "不能返回分类父节点" in prompt[0]["content"]
    original = recognition_fingerprint(taxonomy)
    tree_payload["categories"][1]["name"] = "保暖效果"
    assert (
        recognition_fingerprint(TaxonomyConfig.model_validate(tree_payload)) != original
    )


def test_parent_and_foreign_labels_cannot_be_classified(tree_payload):
    taxonomy = TaxonomyConfig.model_validate(tree_payload)
    payload = ModelClassification.model_validate(
        {
            "semantic_units": [
                {
                    "subject": "PRODUCT",
                    "label_code": code,
                    "opinion": "功能不好",
                    "sentiment": "NEGATIVE",
                    "assertion": "AFFIRMED",
                    "part": "UNSPECIFIED",
                    "evidence": "功能不好",
                    "implicit": False,
                }
                for code in ["FUNCTION", "FOREIGN"]
            ]
        }
    )
    result = validate_classification(
        "key",
        "功能不好",
        "",
        payload,
        taxonomy,
        ListingClaimsConfig(version="v1", claims=[]),
        "test",
        "test",
    )
    assert not result.semantic_units
    assert "未知标签: FUNCTION" in result.review_reasons
    assert "未知标签: FOREIGN" in result.review_reasons


def _registry(*taxonomies):
    return CapabilityRegistry(
        "test",
        tuple(
            CategoryCapability(
                key=f"source-{index}",
                agent_family="test",
                logic_version="v1",
                model_policy=ModelPolicy("v1", "primary", None),
                variants=(),
                taxonomy=taxonomy,
            )
            for index, taxonomy in enumerate(taxonomies)
        ),
    )


def test_combined_tree_retains_paths_and_refuses_cross_framework_collision(
    tree_payload,
):
    taxonomy = TaxonomyConfig.model_validate(tree_payload)
    legacy = load_taxonomy(Path("config/taxonomy_eyewear.json"))
    combined = _registry(taxonomy, legacy).combined_taxonomy()
    assert label_path(combined, "COLD") == ["功能", "保暖性", "不保暖"]
    assert combined.structure_version == 2
    with pytest.raises(ValueError, match="不同框架"):
        _registry(taxonomy, taxonomy).combined_taxonomy()


def test_new_framework_does_not_apply_legacy_claim_aliases(tree_payload):
    taxonomy = TaxonomyConfig.model_validate(tree_payload)
    claims = ListingClaimsConfig.model_validate(
        {
            "version": "v1",
            "claims": [
                {
                    "claim_id": "CLAIM",
                    "text": "测试承诺",
                    "source": "测试",
                    "allowed_label_codes": ["OLD_CODE"],
                }
            ],
        }
    )
    assert adapt_claims_to_taxonomy(claims, taxonomy) is claims
