from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
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


def test_cold_load_does_not_block_another_cached_dataset(tmp_path, monkeypatch):
    returns, products = _write_inputs(tmp_path)
    monkeypatch.setattr(dataset_cache, "_cache", OrderedDict())
    args = (str(returns), str(products), "", None, "auto", "r", "p")
    hot = dataset_cache.load_cached_dataset(*args)
    entered, release = Event(), Event()
    original = dataset_cache.load_return_dataset_auto

    def slow_load(*values, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(*values, **kwargs)

    monkeypatch.setattr(dataset_cache, "load_return_dataset_auto", slow_load)
    with ThreadPoolExecutor(max_workers=2) as executor:
        cold = executor.submit(dataset_cache.load_cached_dataset, *args[:-1], "new")
        try:
            assert entered.wait(2)
            cached = executor.submit(dataset_cache.load_cached_dataset, *args)
            assert cached.result(timeout=1) is hot
        finally:
            release.set()
        assert cold.result(timeout=3) is not hot
    assert not dataset_cache._loading


def test_failed_load_releases_waiters_and_can_retry(tmp_path, monkeypatch):
    returns, products = _write_inputs(tmp_path)
    monkeypatch.setattr(dataset_cache, "_cache", OrderedDict())
    args = (str(returns), str(products), "", None, "auto", "r", "p")
    entered, release, waiting = Event(), Event(), Event()
    original_loader = dataset_cache.load_return_dataset_auto
    original_result = dataset_cache.Future.result

    def fail(*values, **kwargs):
        entered.set()
        assert release.wait(3)
        raise ValueError("合成加载失败")

    def await_result(future, *values, **kwargs):
        waiting.set()
        return original_result(future, *values, **kwargs)

    monkeypatch.setattr(dataset_cache, "load_return_dataset_auto", fail)
    with ThreadPoolExecutor(max_workers=2) as executor:
        owner = executor.submit(dataset_cache.load_cached_dataset, *args)
        assert entered.wait(2)
        with monkeypatch.context() as scoped:
            scoped.setattr(dataset_cache.Future, "result", await_result)
            follower = executor.submit(dataset_cache.load_cached_dataset, *args)
            try:
                assert waiting.wait(2)
            finally:
                release.set()
            for future in (owner, follower):
                with pytest.raises(ValueError, match="合成加载失败"):
                    future.result(timeout=3)
    assert not dataset_cache._loading
    assert not dataset_cache._cache
    monkeypatch.setattr(dataset_cache, "load_return_dataset_auto", original_loader)
    assert dataset_cache.load_cached_dataset(*args) is not None
