from pathlib import Path

from return_semantics.capabilities import load_capability_registry
from return_semantics.data import load_return_dataset
from return_semantics.task_plan import build_category_execution_plan

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_real_seekway_us_data_matches_business_baseline(
    seekway_business_baseline_files: tuple[Path, Path],
) -> None:
    returns_path, products_path = seekway_business_baseline_files
    dataset = load_return_dataset(
        returns_path,
        products_path,
        store="SEEKWAY:US",
    )

    assert len(dataset.mskus) == 2410
    assert len(dataset.records) == 108397
    assert int(dataset.records["has_text_evidence"].sum()) == 93704
    assert len(dataset.unique_comments) == 37373
    assert int(dataset.records["product_match_status"].eq("matched").sum()) == 108017
    assert int(dataset.records["product_match_status"].eq("unmatched").sum()) == 380

    registry = load_capability_registry(
        PROJECT_ROOT / "config" / "category_capabilities.json"
    )
    plan = build_category_execution_plan(
        dataset,
        registry,
        store="SEEKWAY:US",
    ).summary
    assert plan["executable_count"] == 37257
    assert plan["executable_record_count"] == 93586
    assert plan["excluded_count"] == 116
    assert plan["excluded_record_count"] == 118
    assert plan["unmatched_product_count"] == 116
    assert plan["missing_category_count"] == 0
    assert plan["unknown_category_count"] == 0
