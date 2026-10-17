"""复用不可变数据快照的解析与商品匹配结果。"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from concurrent.futures import Future
from pathlib import Path
from time import perf_counter

from return_semantics.analysis_context import RETURNS_CONTEXT, AnalysisContext
from return_semantics.data import (
    ReturnDataset,
    load_return_dataset,
    load_return_dataset_auto,
)
from web_backend.database import Database
from web_backend.datasets.product_store import load_product_frame

_DATASET_CACHE_CAPACITY = 8

_cache: OrderedDict[tuple[str, ...], ReturnDataset] = OrderedDict()
_lock = threading.RLock()
_loading: dict[tuple[str, ...], Future[ReturnDataset]] = {}
performance_logger = logging.getLogger("uvicorn.error.performance")


def load_cached_dataset(
    return_file_path: str,
    product_file_path: str,
    store: str,
    listing: str | None,
    scope_mode: str,
    return_sha256: str,
    product_sha256: str,
    analysis_context: AnalysisContext = RETURNS_CONTEXT,
    *,
    database: Database | None = None,
) -> ReturnDataset:
    """调用方只读共享结果；需要修改数据时先复制对应的 DataFrame。"""
    automatic = scope_mode == "auto"
    key = (
        str(database.path.resolve()) if database else "",
        return_file_path,
        product_file_path,
        return_sha256,
        product_sha256,
        scope_mode,
        analysis_context,
        "" if automatic else store,
        "" if automatic else (listing or ""),
        *(
            f"{stat.st_mtime_ns}:{stat.st_size}"
            for stat in (
                Path(return_file_path).stat(),
                Path(product_file_path).stat(),
            )
        ),
    )
    waiting = perf_counter()
    with _lock:
        acquired = perf_counter()
        dataset = _cache.get(key)
        cache_hit = dataset is not None
        pending = _loading.get(key)
        owner = dataset is None and pending is None
        if owner:
            pending = Future()
            _loading[key] = pending
        if cache_hit:
            _cache.move_to_end(key)
    if dataset is None:
        assert pending is not None
        if owner:
            try:
                product_source = (
                    load_product_frame(database, Path(product_file_path))
                    if database
                    else Path(product_file_path)
                )
                if automatic:
                    dataset = load_return_dataset_auto(
                        Path(return_file_path),
                        product_source,
                        analysis_context=analysis_context,
                    )
                else:
                    dataset = load_return_dataset(
                        Path(return_file_path),
                        product_source,
                        store=store,
                        listing=listing,
                        analysis_context=analysis_context,
                    )
            except BaseException as error:
                # 失败唤醒同键等待者，后续请求仍可重新加载。
                with _lock:
                    _loading.pop(key)
                    pending.set_exception(error)
                raise
            with _lock:
                _cache[key] = dataset
                while len(_cache) > _DATASET_CACHE_CAPACITY:
                    _cache.popitem(last=False)
                _loading.pop(key)
                pending.set_result(dataset)
        else:
            dataset = pending.result()
    performance_logger.info(
        "dataset_cache hit=%s wait_ms=%.2f load_ms=%.2f records=%s groups=%s",
        cache_hit,
        (acquired - waiting) * 1000,
        (perf_counter() - acquired) * 1000,
        len(dataset.records),
        len(dataset.unique_comments),
    )
    return dataset
