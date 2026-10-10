from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock

import pytest
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


@pytest.mark.parametrize("scope_mode", ["auto", "manual"])
def test_dataset_cache_keeps_analysis_contexts_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope_mode: str
) -> None:
    returns, products = _write_inputs(tmp_path)
    monkeypatch.setattr(dataset_cache, "_cache", OrderedDict())
    loader_name = (
        "load_return_dataset_auto" if scope_mode == "auto" else "load_return_dataset"
    )
    loader = MagicMock(wraps=getattr(dataset_cache, loader_name))
    monkeypatch.setattr(dataset_cache, loader_name, loader)
    args = (
        str(returns),
        str(products),
        "SEEKWAY:US",
        "L1",
        scope_mode,
        "returns",
        "products",
    )
    contexts = ("returns", "review", "user_feedback")
    datasets = {}
    for context in contexts:
        dataset = dataset_cache.load_cached_dataset(*args, context)
        assert (
            dataset_cache.load_cached_dataset(*args, analysis_context=context)
            is dataset
        )
        datasets[context] = dataset
    assert len({id(dataset) for dataset in datasets.values()}) == 3
    assert loader.call_count == 3
    assert [call.kwargs["analysis_context"] for call in loader.call_args_list] == list(
        contexts
    )
    assert dataset_cache.load_cached_dataset(*args) is datasets["returns"]
    assert loader.call_count == 3
