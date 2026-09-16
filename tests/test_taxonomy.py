from pathlib import Path

from return_semantics.taxonomy import load_taxonomy, validate_taxonomy_claims

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_taxonomy_and_claims_are_consistent(taxonomy, claims) -> None:
    validate_taxonomy_claims(taxonomy, claims)

    assert len(taxonomy.labels) == 72
    assert len(claims.claims) == 13

    labels = {label.code: label for label in taxonomy.labels}
    assert all(label.keywords for label in taxonomy.labels)
    assert "size chart" in labels["SIZE_CHART_GUIDANCE"].keywords
    assert labels["OTHER_USE_SCENARIO"].name == "适用或不适用场景"
    assert "部位字段使用 UNSPECIFIED" in labels["EXPERIENCE_THIN"].description


def test_water_shoe_framework_separates_faults_and_positive_feedback(taxonomy):
    labels = {label.code: label for label in taxonomy.labels}
    assert taxonomy.version == "water-shoes-2026-09-06-v3"
    assert {"SEAM", "INSTEP", "LINING", "DRAINAGE_HOLE"} <= set(taxonomy.allowed_parts)
    assert {
        "QUALITY_SEAM_FAILURE",
        "QUALITY_TEAR",
        "QUALITY_HOLE",
        "QUALITY_WEAR",
        "FUNCTION_QUICK_DRY",
        "FUNCTION_DRAINAGE",
        "FUNCTION_SUPPORT",
        "FUNCTION_CUSHION",
        "EXPERIENCE_COMFORT",
        "EXPERIENCE_WEIGHT",
        "OTHER_CUSTOMER_SERVICE",
        "OTHER_DELIVERY_SPEED",
        "SIZE_REQUEST",
    } <= labels.keys()
    assert (
        not {
            "QUALITY_STITCH_TEAR",
            "QUALITY_HOLE_WEAR",
            "FUNCTION_DRY_DRAINAGE",
            "EXPERIENCE_COMFORT_LIGHTWEIGHT",
            "OTHER_LOGISTICS_SERVICE",
        }
        & labels.keys()
    )
    assert labels["QUALITY_COLORFAST_POSITIVE"].allowed_sentiments == ["POSITIVE"]
    assert labels["FUNCTION_SAND_RESISTANCE"].allowed_sentiments == ["POSITIVE"]
    assert labels["VALUE_FOR_MONEY"].group == "其他原因"


def test_eyewear_taxonomy_matches_reviewed_framework() -> None:
    taxonomy = load_taxonomy(PROJECT_ROOT / "config" / "taxonomy_eyewear.json")
    labels = {label.code: label for label in taxonomy.labels}
    assert taxonomy.version == "eyewear-unified-2026-09-06-v1-semantic1"
    assert len(taxonomy.labels) == 39
    assert len({label.group for label in taxonomy.labels}) == 7
    assert labels["EYEWEAR_BUYER_REASON_V2_U1"].allowed_sentiments == ["NEUTRAL"]
    assert labels["EYEWEAR_FOGGING_PERFORMANCE_U1"].allowed_sentiments == [
        "NEGATIVE",
        "POSITIVE",
    ]
    assert "EYEWEAR_FRAME_DEFORMATION_U1" in labels
    assert "EYEWEAR_AGE_MISMATCH" not in labels
    assert "EYEWEAR_FOGGING_POSITIVE" not in labels
