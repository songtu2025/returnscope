"""复用不可变数据快照的解析与商品匹配结果。"""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

from return_semantics.analysis_context import RETURNS_CONTEXT, AnalysisContext
from return_semantics.data import (
    ReturnDataset,
    load_return_dataset,
    load_return_dataset_auto,
)

_cache: OrderedDict[tuple[str, ...], ReturnDataset] = OrderedDict()
_lock = threading.RLock()


def load_cached_dataset(
    return_file_path: str,
    product_file_path: str,
    store: str,
    listing: str | None,
    scope_mode: str,
    return_sha256: str,
    product_sha256: str,
    analysis_context: AnalysisContext = RETURNS_CONTEXT,
) -> ReturnDataset:
    """调用方只读共享结果；需要修改数据时先复制对应的 DataFrame。"""
    automatic = scope_mode == "auto"
    key = (
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
    with _lock:
        dataset = _cache.get(key)
        if dataset is None:
            if automatic:
                dataset = load_return_dataset_auto(
                    Path(return_file_path),
                    Path(product_file_path),
                    analysis_context=analysis_context,
                )
            else:
                dataset = load_return_dataset(
                    Path(return_file_path),
                    Path(product_file_path),
                    store=store,
                    listing=listing,
                    analysis_context=analysis_context,
                )
            _cache[key] = dataset
        _cache.move_to_end(key)
        while len(_cache) > 8:
            _cache.popitem(last=False)
        return dataset
