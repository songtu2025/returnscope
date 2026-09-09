from pathlib import Path

import pandas as pd
import pytest

from return_semantics.capabilities import load_capability_registry
from return_semantics.model_client import JsonlCache, ModelCallResult, Sub2APISettings
from return_semantics.pipeline import classify_comments
from return_semantics.schemas import (
    ListingClaimsConfig,
    ModelClassification,
    SentimentCode,
)
from return_semantics.taxonomy import (
    adapt_claims_to_taxonomy,
    aligned_label_group,
    load_listing_claims,
    load_taxonomy,
    load_taxonomy_alignment,
)
from return_semantics.validator import validate_classification

ROOT = Path(__file__).resolve().parents[1]


def _unit(code, evidence, part="UNSPECIFIED", sentiment="NEGATIVE"):
    return {
        "subject": "PRODUCT",
        "label_code": code,
        "evidence": evidence,
        "opinion": evidence,
        "part": part,
        "sentiment": sentiment,
        "assertion": "AFFIRMED",
        "implicit": False,
    }


def _validate(units, comment, context="review"):
    taxonomy = load_taxonomy(ROOT / "config/taxonomy_eyewear.json")
    result = ModelClassification.model_validate({"semantic_units": units})
    return validate_classification(
        "sample",
        comment,
        "",
        result,
        taxonomy,
        ListingClaimsConfig(version="none", claims=[]),
        "test",
        "test",
        analysis_context=context,
    )


def test_four_categories_share_groups_and_keep_neutral_reasons_explicit():
    registry = load_capability_registry(ROOT / "config/category_capabilities.json")
    groups = load_taxonomy_alignment()["groups"]
    for capability in registry.capabilities:
        taxonomy = registry.load_taxonomy(capability)
        assert taxonomy.validation_rules.allowed_groups == groups
        assert taxonomy.validation_rules.neutral_reason_labels
        assert all(label.group in groups for label in taxonomy.labels)
    combined = registry.combined_taxonomy()
    assert combined.validation_rules.conflict_scope == "evidence"
    assert len(combined.validation_rules.neutral_reason_labels) == 11


def test_glove_framework_topics_extend_taxonomy_compatibly():
    taxonomy = load_taxonomy(ROOT / "config/taxonomy_gloves.json")
    labels = {label.code: label for label in taxonomy.labels}

    assert taxonomy.version == "gloves-unified-2026-09-08-v1-semantic1"
    assert len(labels) == 63
    assert {
        "GLOVE_SIZE_SMALL_U1",
        "GLOVE_FIT_GENERAL_U1",
        "GLOVE_SIZE_REQUEST_U1",
        "GLOVE_SNOW_RESISTANCE_U1",
        "GLOVE_HEATING_EXPECTATION_U1",
        "GLOVE_SWEATING_U1",
        "GLOVE_WORKMANSHIP_U1",
        "GLOVE_PRESSURE_DISCOMFORT_U1",
        "GLOVE_NUMBNESS_U1",
        "GLOVE_PACKAGING_U1",
        "GLOVE_SAME_SIDE_PAIR_U1",
        "GLOVE_DELIVERY_SPEED_U1",
        "GLOVE_PRICE_U1",
        "GLOVE_PURCHASE_INTENT_U1",
    }.issubset(labels)
    assert set(labels["GLOVE_ODOR_U1"].allowed_sentiments) == {
        SentimentCode.NEGATIVE,
        SentimentCode.POSITIVE,
    }
    assert labels["GLOVE_ORDER_WRONG_ITEM_U1"].allowed_sentiments == [
        SentimentCode.NEGATIVE
    ]
    assert set(taxonomy.validation_rules.neutral_reason_labels) == {
        "GLOVE_SIZE_REQUEST_U1",
        "GLOVE_BUYER_REASON_U1",
        "GLOVE_GIFT_REASON_U1",
        "GLOVE_CHEAPER_ALTERNATIVE_U1",
        "GLOVE_PACKAGING_U1",
        "GLOVE_POWER_BUTTON_U1",
    }
    assert set(taxonomy.validation_rules.required_review_labels) == {
        "GLOVE_SIZE_ISSUE_UNSPECIFIED_U1",
        "GLOVE_POWER_BUTTON_U1",
        "GLOVE_REASON_UNSPECIFIED_U1",
    }


def test_review_positive_does_not_require_a_return_reason():
    units = [_unit("EYEWEAR_FOGGING_PERFORMANCE_U1", "Never fogs", "LENS", "POSITIVE")]
    review = _validate(units, "Never fogs")
    returns = _validate(units, "Never fogs", "returns")
    assert review.status == "AUTO_APPROVED"
    assert review.positive_label_codes == ["EYEWEAR_FOGGING_PERFORMANCE_U1"]
    assert review.problem_label_codes == []
    assert returns.status == "SECONDARY_REVIEW"


def test_explicit_neutral_reason_survives_group_rename():
    code = "EYEWEAR_BUYER_REASON_V2_U1"
    result = _validate(
        [_unit(code, "No longer needed", sentiment="NEUTRAL")], "No longer needed"
    )
    assert result.problem_label_codes == [code]
    assert result.primary_label_codes == [code]


def test_generic_negative_requires_review_even_when_model_does_not_request_it():
    code = "EYEWEAR_REASON_UNSPECIFIED_U1"
    result = _validate([_unit(code, "Not as expected")], "Not as expected")
    assert result.status == "MANUAL_REVIEW"
    assert "标签规则要求人工复核" in result.review_reasons
    assert any("语义边界需人工确认" in reason for reason in result.review_reasons)


@pytest.mark.parametrize("independent", [True, False])
def test_conflict_is_scoped_to_overlapping_evidence(independent):
    comment = "The lens fell out. The frame material is poor."
    units = [
        _unit("EYEWEAR_LENS_DETACHMENT_U1", "The lens fell out.", "LENS"),
        _unit(
            "EYEWEAR_QUALITY_GENERAL_U1",
            "The frame material is poor." if independent else "The lens fell out.",
            "FRAME" if independent else "LENS",
        ),
    ]
    result = _validate(units, comment)
    assert (
        any("标签组合" in reason for reason in result.review_reasons) is not independent
    )


def test_positive_and_negative_of_same_topic_both_survive():
    comment = "No fog indoors. Fogs outdoors."
    code = "EYEWEAR_FOGGING_PERFORMANCE_U1"
    result = _validate(
        [
            _unit(code, "No fog indoors.", "LENS", "POSITIVE"),
            _unit(code, "Fogs outdoors.", "LENS"),
        ],
        comment,
    )
    assert result.problem_label_codes == [code]
    assert result.positive_label_codes == [code]
    assert len(result.semantic_units) == 2


def test_claim_mapping_preserves_original_and_only_maps_registered_codes():
    claims = load_listing_claims(ROOT / "config/listing_claims_sk001.json")
    taxonomy = load_taxonomy(ROOT / "config/taxonomy_water_shoes.json")
    before = claims.model_dump()
    adapted = adapt_claims_to_taxonomy(claims, taxonomy)
    assert claims.model_dump() == before
    assert adapted.version == claims.version
    dry = next(claim for claim in adapted.claims if claim.claim_id == "CLM_DRY_01")
    assert set(dry.allowed_label_codes) == {
        "FUNCTION_QUICK_DRY_U1",
        "FUNCTION_DRAINAGE_U1",
    }
    assert (
        aligned_label_group(
            "footwear", "water-shoes-2026-09-06-v3", "FIT_TOO_SMALL", "尺码与合脚"
        )
        == "尺码与适配"
    )
    assert (
        aligned_label_group("footwear", "unregistered", "FIT_TOO_SMALL", "原分组")
        == "原分组"
    )


def test_cache_separates_review_and_returns(tmp_path):
    class Client:
        settings = Sub2APISettings(
            api_key="test", base_url="https://example.test", model="fake"
        )
        calls = 0

        def classify(self, **kwargs):
            self.calls += 1
            return ModelCallResult(
                classification=ModelClassification.model_validate(
                    {
                        "semantic_units": [
                            _unit(
                                "EYEWEAR_FOGGING_PERFORMANCE_U1",
                                "Never fogs",
                                "LENS",
                                "POSITIVE",
                            ),
                        ]
                    }
                ),
                model_name="fake",
                usage={},
            )

    client = Client()
    arguments = dict(
        unique_comments=pd.DataFrame(
            [
                {
                    "classification_key": "one",
                    "comment_normalized": "Never fogs",
                    "reason": "",
                }
            ]
        ),
        taxonomy=load_taxonomy(ROOT / "config/taxonomy_eyewear.json"),
        claims=ListingClaimsConfig(version="none", claims=[]),
        client=client,
        cache=JsonlCache(tmp_path / "cache.jsonl"),
    )
    for context in ("review", "returns", "review"):
        run = classify_comments(**arguments, analysis_context=context)
    assert client.calls == 2
    assert run.cache_hits == 1
    assert run.classifications["one"].status == "AUTO_APPROVED"
