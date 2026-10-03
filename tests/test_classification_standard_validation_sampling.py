from copy import deepcopy

import pytest

from web_backend.classification_standards.validation_sampling import (
    ClassificationStandardValidationSamplingMixin,
    _take_bucket_samples,
)


@pytest.mark.parametrize(
    ("sample_size", "expected"),
    [
        (4, ["c01", "c02", "c06", "c03"]),
        (20, ["c01", "c02", "c06", "c03", "c05", "c04"]),
    ],
)
def test_store_sampling_preserves_weighted_round_robin_order(
    sample_size: int, expected: list[str]
) -> None:
    items = [
        {"classification_key": "c04", "store": "Z", "listing": "L"},
        {"classification_key": "c06", "store": "B", "listing": "L"},
        {"classification_key": "c05", "store": "A", "listing": "L"},
        {"classification_key": "c01", "store": "Z", "listing": "L"},
        {"classification_key": "c03", "store": "Z", "listing": "L"},
        {"classification_key": "c02", "store": "A", "listing": "L"},
    ]
    original = deepcopy(items)

    sampled = ClassificationStandardValidationSamplingMixin._round_robin_samples(
        items, sample_size, bucket_fields=("store", "listing")
    )

    assert [item["classification_key"] for item in sampled] == expected
    assert items == original


def test_store_sampling_breaks_equal_bucket_sizes_by_store_and_listing() -> None:
    items = [
        {"classification_key": "c04", "store": "Z", "listing": "L1"},
        {"classification_key": "c03", "store": "A", "listing": "L2"},
        {"classification_key": "c02", "store": "A", "listing": "L1"},
        {"classification_key": "c01", "store": "Z", "listing": "L1"},
        {"classification_key": "c05", "store": "A", "listing": "L2"},
        {"classification_key": "c06", "store": "A", "listing": "L1"},
    ]

    sampled = ClassificationStandardValidationSamplingMixin._round_robin_samples(
        items, 20, bucket_fields=("store", "listing")
    )

    assert [item["classification_key"] for item in sampled] == [
        "c02",
        "c03",
        "c01",
        "c06",
        "c05",
        "c04",
    ]


def test_primary_label_buckets_keep_missing_labels_and_weighted_order() -> None:
    buckets = {
        "Z": [{"classification_key": "c01"}, {"classification_key": "c04"}],
        "A": [{"classification_key": "c02"}, {"classification_key": "c05"}],
        "__NO_PRIMARY_LABEL__": [{"classification_key": "c03"}],
    }

    sampled = _take_bucket_samples(buckets, 20)

    assert [item["classification_key"] for item in sampled] == [
        "c02",
        "c01",
        "c03",
        "c05",
        "c04",
    ]
