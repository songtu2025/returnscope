from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock

from test_task_planning import _write_inputs

from web_backend import dataset_cache


def test_parallel_loads_share_matching_and_hash_changes_reload(
    tmp_path: Path, monkeypatch
):
    returns, products = _write_inputs(tmp_path)
    monkeypatch.setattr(dataset_cache, "_cache", OrderedDict())
    loader = MagicMock(wraps=dataset_cache.load_return_dataset_auto)
    monkeypatch.setattr(dataset_cache, "load_return_dataset_auto", loader)
    args = (str(returns), str(products), "", None, "auto", "returns-v1", "products-v1")
    with ThreadPoolExecutor(max_workers=3) as executor:
        datasets = list(
            executor.map(lambda _: dataset_cache.load_cached_dataset(*args), range(3))
        )
    assert loader.call_count == 1
    assert datasets[0] is datasets[1] is datasets[2]
    automatic_scope = (*args[:2], "任意店铺", "任意Listing", *args[4:])
    assert dataset_cache.load_cached_dataset(*automatic_scope) is datasets[0]
    changed = dataset_cache.load_cached_dataset(*args[:-1], "products-v2")
    assert loader.call_count == 2
    assert changed is not datasets[0]
    returns.write_text(
        returns.read_text(encoding="utf-8-sig") + "\n", encoding="utf-8-sig"
    )
    assert dataset_cache.load_cached_dataset(*args[:-1], "products-v2") is not changed
    assert loader.call_count == 3


def test_dataset_cache_evicts_old_entries(tmp_path: Path, monkeypatch):
    returns, products = _write_inputs(tmp_path)
    monkeypatch.setattr(dataset_cache, "_cache", OrderedDict())
    loader = MagicMock(wraps=dataset_cache.load_return_dataset_auto)
    monkeypatch.setattr(dataset_cache, "load_return_dataset_auto", loader)
    for version in range(9):
        dataset_cache.load_cached_dataset(
            str(returns), str(products), "", None, "auto", "r", str(version)
        )
    assert len(dataset_cache._cache) == 8
    dataset_cache.load_cached_dataset(
        str(returns), str(products), "", None, "auto", "r", "0"
    )
    assert loader.call_count == 10
