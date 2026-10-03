from __future__ import annotations

from collections.abc import Iterable
from datetime import date

import pandas as pd

from return_analysis.calculations.common import label_codes, split_values


def filter_details(
    frame: pd.DataFrame,
    start_date: date | None = None,
    end_date: date | None = None,
    skus: Iterable[str] = (),
    asins: Iterable[str] = (),
    category_as: Iterable[str] = (),
    category_bs: Iterable[str] = (),
    listings: Iterable[str] = (),
    styles: Iterable[str] = (),
    sizes: Iterable[str] = (),
    reasons: Iterable[str] = (),
    statuses: Iterable[str] = (),
    problem_codes: Iterable[str] = (),
    claim_relations: Iterable[str] = (),
) -> pd.DataFrame:
    result = frame.copy()
    if start_date is not None:
        result = result.loc[result["return_date"].dt.date >= start_date]
    if end_date is not None:
        result = result.loc[result["return_date"].dt.date <= end_date]

    filters = (
        ("sku", set(skus)),
        ("asin", set(asins)),
        ("品类A", set(category_as)),
        ("品类B", set(category_bs)),
        ("Listing", set(listings)),
        ("款式", set(styles)),
        ("尺码", set(sizes)),
        ("Amazon原因", set(reasons)),
        ("处理状态", set(statuses)),
    )
    for column, selected in filters:
        if selected:
            result = result.loc[result[column].isin(selected)]

    selected_codes = set(problem_codes)
    if selected_codes:
        result = result.loc[
            result["问题标签"].map(
                lambda value: bool(selected_codes.intersection(label_codes(value)))
            )
        ]

    selected_relations = set(claim_relations)
    if selected_relations:
        result = result.loc[
            result["Listing承诺关系"].map(
                lambda value: bool(selected_relations.intersection(split_values(value)))
            )
        ]
    return result.copy()
