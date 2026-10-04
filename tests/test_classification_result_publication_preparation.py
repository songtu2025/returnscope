from copy import deepcopy
from dataclasses import replace

import pandas as pd
import pytest
from test_classification_result_publication_state import publication as publication

from web_backend.classification_results.publication_preparation import (
    prepare_labels,
    prepare_publication,
)


def test_preparation_keeps_source_rows_and_does_not_mutate_inputs(publication) -> None:
    seed = publication.seed
    seed.dataset = replace(seed.dataset, records=seed.dataset.records.iloc[::-1].copy())
    before_records = seed.dataset.records.copy(deep=True)
    before_comments = seed.dataset.unique_comments.copy(deep=True)
    before_results = deepcopy(seed.results)

    prepared = prepare_publication(seed.dataset, seed.results, seed.taxonomy)

    assert [row["source_row"] for row in prepared["records"]] == [2, 3, 4]
    assert [row["order_id"] for row in prepared["records"]] == [
        "ORDER-DUP",
        "ORDER-DUP",
        "ORDER-OTHER",
    ]
    assert prepared["store_site"] == "SEEKWAY:US"
    assert prepared["listing"] == "L1"
    assert prepared["units"][0]["record_count"] == 3
    classification = prepared["units"][0]["classification"]
    assert "semantic_disposition" not in classification
    assert all(
        "label_path" not in unit and "label_code_path" not in unit
        for unit in classification["semantic_units"]
    )
    pd.testing.assert_frame_equal(seed.dataset.records, before_records)
    pd.testing.assert_frame_equal(seed.dataset.unique_comments, before_comments)
    assert seed.results == before_results


def test_labels_keep_key_kind_and_code_order_with_deduplication(publication) -> None:
    seed = publication.seed
    result = next(iter(seed.results.values())).model_copy(
        update={
            "problem_label_codes": ["Z", "A", "Z"],
            "positive_label_codes": ["Z", "Z"],
            "primary_label_codes": ["A"],
        }
    )
    labels = prepare_labels({"z-key": result, "a-key": result}, seed.taxonomy)

    assert [
        (item["classification_key"], item["label_kind"], item["label_code"])
        for item in labels
    ] == [
        (key, kind, code)
        for key in ["a-key", "z-key"]
        for kind, code in [
            ("problem", "A"),
            ("problem", "Z"),
            ("positive", "Z"),
            ("primary", "A"),
        ]
    ]
    assert all(
        item["label_name"] is None and item["label_group"] is None for item in labels
    )


@pytest.mark.parametrize("mixed", [False, True])
def test_preparation_does_not_choose_a_scope_for_empty_or_mixed_records(
    publication, mixed
) -> None:
    seed = publication.seed
    results = seed.results if mixed else {}
    if mixed:
        seed.dataset.records.loc[seed.dataset.records.index[0], "listing"] = "L2"

    prepared = prepare_publication(seed.dataset, results, seed.taxonomy)

    assert prepared["store_site"] is None
    assert prepared["listing"] is None
    assert len(prepared["records"]) == (3 if mixed else 0)
