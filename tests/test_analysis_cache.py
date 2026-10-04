import pickle
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from return_analysis.data import PRODUCT_DIMENSION_COLUMNS, AnalysisData
from web_backend.analysis_services import cache
from web_backend.analysis_services.task_data import (
    ANALYSIS_CACHE_VERSION,
    _AnalysisTaskData,
)


@pytest.fixture(autouse=True)
def clear_memory_cache():
    _AnalysisTaskData._cached_load.cache_clear()
    yield
    _AnalysisTaskData._cached_load.cache_clear()


@pytest.fixture
def data() -> AnalysisData:
    return AnalysisData(
        details=pd.DataFrame([{"sku": "SYNTHETIC-SKU", "Listing": "原始合成Listing"}]),
        semantics=pd.DataFrame([{"分类键": "SYNTHETIC"}]),
        unknowns=pd.DataFrame(),
        label_catalog=pd.DataFrame(),
        products=pd.DataFrame(),
    )


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    result, product = tmp_path / "synthetic.xlsx", tmp_path / "synthetic-products.xlsx"
    result.touch()
    product.touch()
    return result, product, result.with_suffix(".web-cache.pkl")


def _load(result: Path, product: Path, result_mtime: int = 1) -> AnalysisData:
    return _AnalysisTaskData._cached_load(
        str(result), result_mtime, str(product), 2, "SYNTHETIC"
    )


@pytest.mark.parametrize(
    "initial", ["missing", "stale", "wrong_type", "corrupt", "empty"]
)
def test_invalid_disk_cache_reloads_and_replaces_file(
    tmp_path, monkeypatch, data, initial
):
    result, product, cache_path = _paths(tmp_path)
    key = (ANALYSIS_CACHE_VERSION, 1, str(product.resolve()), 2, "SYNTHETIC")
    if initial in {"stale", "wrong_type"}:
        cache_path.write_bytes(
            pickle.dumps(
                (
                    ("stale",) if initial == "stale" else key,
                    data if initial == "stale" else {},
                )
            )
        )
    elif initial == "corrupt":
        cache_path.write_bytes(b"synthetic-corrupted-cache")
    elif initial == "empty":
        cache_path.touch()
    read = Mock(return_value=data)
    monkeypatch.setattr(cache, "load_analysis_data", read)
    monkeypatch.setattr(
        cache, "load_product_dimensions", Mock(return_value=pd.DataFrame())
    )

    actual = _load(result, product)

    assert actual is data
    read.assert_called_once_with(result)
    stored_key, stored_data = pickle.loads(cache_path.read_bytes())
    assert stored_key == key and isinstance(stored_data, AnalysisData)
    pd.testing.assert_frame_equal(stored_data.details, data.details)


def test_disk_hit_does_not_read_workbooks(tmp_path, monkeypatch, data):
    result, product, cache_path = _paths(tmp_path)
    key = (ANALYSIS_CACHE_VERSION, 1, str(product.resolve()), 2, "SYNTHETIC")
    cache_path.write_bytes(pickle.dumps((key, data)))
    read = Mock(side_effect=AssertionError("不应读取工作簿"))
    monkeypatch.setattr(cache, "load_analysis_data", read)

    actual = _load(result, product)

    pd.testing.assert_frame_equal(actual.details, data.details)
    read.assert_not_called()


def test_memory_hit_and_changed_mtime_keep_cache_key_contract(
    tmp_path, monkeypatch, data
):
    result, product, _ = _paths(tmp_path)
    read = Mock(return_value=data)
    monkeypatch.setattr(cache, "load_analysis_data", read)
    monkeypatch.setattr(
        cache, "load_product_dimensions", Mock(return_value=pd.DataFrame())
    )

    first = _load(result, product)
    assert _load(result, product) is first
    _load(result, product, result_mtime=3)

    assert read.call_count == 2
    assert _AnalysisTaskData._cached_load.cache_info().maxsize == 4


@pytest.mark.parametrize("failure", [KeyError, ValueError])
def test_product_validation_failure_keeps_original_data(
    tmp_path, monkeypatch, data, failure
):
    result, product, _ = _paths(tmp_path)
    monkeypatch.setattr(cache, "load_analysis_data", Mock(return_value=data))
    monkeypatch.setattr(
        cache, "load_product_dimensions", Mock(side_effect=failure("合成产品错误"))
    )

    assert _load(result, product) is data


def test_product_dimensions_replace_existing_values_without_mutating_input(
    tmp_path, monkeypatch, data
):
    result, product, _ = _paths(tmp_path)
    row = dict.fromkeys(PRODUCT_DIMENSION_COLUMNS, " 合成维度 ")
    row.update(sku="SYNTHETIC-SKU", Listing=" 新合成Listing ")
    products = pd.DataFrame([row])
    before = data.details.copy(deep=True)
    read_products = Mock(return_value=products)
    monkeypatch.setattr(cache, "load_analysis_data", Mock(return_value=data))
    monkeypatch.setattr(cache, "load_product_dimensions", read_products)

    actual = _load(result, product)

    assert actual.details["Listing"].tolist() == ["新合成Listing"]
    assert actual.semantics is data.semantics and actual.products is products
    pd.testing.assert_frame_equal(data.details, before)
    assert read_products.call_args.args[0] == product
    assert list(read_products.call_args.args[1]) == ["SYNTHETIC-SKU"]
    assert read_products.call_args.kwargs == {"store": "SYNTHETIC"}


def test_failed_atomic_replace_returns_data_and_cleans_temporary_file(
    tmp_path, monkeypatch, data
):
    result, product, cache_path = _paths(tmp_path)
    monkeypatch.setattr(cache, "load_analysis_data", Mock(return_value=data))
    monkeypatch.setattr(
        cache, "load_product_dimensions", Mock(return_value=pd.DataFrame())
    )
    monkeypatch.setattr(Path, "replace", Mock(side_effect=OSError("合成缓存写入失败")))

    assert _load(result, product) is data

    assert not cache_path.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_unexpected_product_error_propagates_without_writing_cache(
    tmp_path, monkeypatch, data
):
    result, product, cache_path = _paths(tmp_path)
    monkeypatch.setattr(cache, "load_analysis_data", Mock(return_value=data))
    monkeypatch.setattr(
        cache, "load_product_dimensions", Mock(side_effect=RuntimeError("合成运行错误"))
    )

    with pytest.raises(RuntimeError, match="合成运行错误"):
        _load(result, product)

    assert not cache_path.exists()
