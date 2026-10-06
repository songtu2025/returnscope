from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from web_backend.tasks.product_resolution import TaskProductResolutionMixin


def _dataset(rows, mode="auto"):
    records = pd.DataFrame(rows)
    records["has_text_evidence"] = True
    unique = records[["classification_key"]].drop_duplicates()
    return SimpleNamespace(records=records, unique_comments=unique, scope_mode=mode)


def _row(key, sku, store="S1", **changes):
    return {
        "classification_key": key,
        "sku": sku,
        "store": store,
        "category_a": "",
        "category_b": "",
        "product_name": "nan",
        **changes,
    }


def _plan(dataset, assignments=None):
    return SimpleNamespace(
        assignments=assignments or ["unknown"] * len(dataset.unique_comments),
        unresolved_classification_keys=lambda _: dataset.unique_comments[
            "classification_key"
        ].tolist(),
    )


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({"sku": ""}, "missing_product_key"),
        ({"sku": "KNOWN"}, "missing_category"),
        ({"sku": "KNOWN", "category_b": "其他"}, "unsupported_category"),
        ({"sku": "LONG-PREFIX-item"}, "product_not_found"),
    ],
)
def test_product_diagnostics_and_longest_listing_prefix(
    tmp_path, monkeypatch, changes, expected
):
    dimensions = pd.DataFrame(
        {"MSKU": ["KNOWN", "OTHER"], "Listing": ["LONG", "LONG-PREFIX"]}
    )
    loader = Mock(return_value=dimensions)
    monkeypatch.setattr(
        "web_backend.tasks.product_resolution.load_product_dimensions", loader
    )
    dataset = _dataset([_row("a", **changes)])
    result = TaskProductResolutionMixin()._unresolved_products(
        dataset, _plan(dataset), tmp_path / "products", "AUTO", None
    )
    assert result[0]["issue"] == expected
    assert result[0]["suggested_listing"] == (
        "LONG" if changes["sku"] == "KNOWN" else "LONG-PREFIX" if changes["sku"] else ""
    )
    assert result[0]["product_key"] == "S1/" + changes["sku"]
    assert result[0]["editable"] == bool(changes["sku"])


@pytest.mark.parametrize("mode, listing", [("auto", None), ("manual", "L1")])
def test_store_cache_is_per_request_and_counts_and_sort_are_preserved(
    tmp_path, monkeypatch, mode, listing
):
    loader = Mock(return_value=pd.DataFrame({"MSKU": ["KNOWN"], "Listing": ["L1"]}))
    monkeypatch.setattr(
        "web_backend.tasks.product_resolution.load_product_dimensions", loader
    )
    dataset = _dataset(
        [
            _row("a", "FIRST"),
            _row("b", "FIRST", product_name="首个商品"),
            _row("b", "FIRST", product_name="后续商品"),
            _row("c", "SECOND"),
            _row("d", "THIRD", store="S2"),
        ],
        mode,
    )
    resolver = TaskProductResolutionMixin()
    first = resolver._unresolved_products(
        dataset, _plan(dataset), tmp_path / "products", "AUTO", "L1"
    )
    second = resolver._unresolved_products(
        dataset, _plan(dataset), tmp_path / "products", "AUTO", "L1"
    )
    assert first == second
    assert [(x["msku"], x["comment_count"], x["record_count"]) for x in first] == [
        ("FIRST", 2, 3),
        ("SECOND", 1, 1),
        ("THIRD", 1, 1),
    ]
    assert first[0]["product_name"] == "首个商品"
    assert [(x.args[1], x.args[2]) for x in loader.call_args_list] == [
        ("S1", listing),
        ("S2", listing),
    ] * 2


def test_resolution_requires_aligned_assignments_before_loading_dimensions(
    tmp_path, monkeypatch
):
    dataset = _dataset([_row("a", "UNKNOWN"), _row("b", "UNKNOWN")])
    loader = Mock()
    monkeypatch.setattr(
        "web_backend.tasks.product_resolution.load_product_dimensions", loader
    )
    with pytest.raises(ValueError, match="zip"):
        TaskProductResolutionMixin()._unresolved_products(
            dataset, _plan(dataset, ["excluded"]), tmp_path / "products", "AUTO", None
        )
    loader.assert_not_called()
