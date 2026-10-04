from __future__ import annotations

import pickle
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from return_analysis.data import (
    PRODUCT_DIMENSION_COLUMNS,
    AnalysisData,
    load_analysis_data,
    load_product_dimensions,
)


def _read_cached_data(
    cache_path: Path, cache_key: tuple[Any, ...]
) -> AnalysisData | None:
    try:
        with cache_path.open("rb") as cache_file:
            stored_key, cached_data = pickle.load(cache_file)
        if stored_key == cache_key and isinstance(cached_data, AnalysisData):
            return cached_data
    except (OSError, EOFError, pickle.PickleError, ValueError, TypeError):
        pass
    return None


def _load_product_data(result: Path, product: Path, store: str) -> AnalysisData:
    data = load_analysis_data(result)
    try:
        products = load_product_dimensions(
            product,
            data.details["sku"].unique(),
            store=store,
        )
    except (KeyError, ValueError):
        products = pd.DataFrame()
    if not products.empty:
        dimensions = set(PRODUCT_DIMENSION_COLUMNS[1:])
        details = data.details.drop(
            columns=[column for column in dimensions if column in data.details],
        ).merge(products, on="sku", how="left", validate="many_to_one")
        for column in dimensions:
            details[column] = details[column].fillna("").astype(str).str.strip()
        data = AnalysisData(
            details=details,
            semantics=data.semantics,
            unknowns=data.unknowns,
            label_catalog=data.label_catalog,
            products=products,
        )
    return data


def _write_cached_data(
    cache_path: Path, cache_key: tuple[Any, ...], data: AnalysisData
) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=cache_path.parent,
            prefix=f"{cache_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as cache_file:
            temp_path = Path(cache_file.name)
            pickle.dump(
                (cache_key, data),
                cache_file,
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        temp_path.replace(cache_path)
    except (OSError, pickle.PickleError):
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
