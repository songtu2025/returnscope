from typing import Any

import pandas as pd


def update_category_rows(
    frame: pd.DataFrame,
    matching: list[Any],
    item: dict[str, str],
    before_items: list[dict[str, Any]],
) -> None:
    before_items.append(
        {
            "msku": item["msku"],
            "store": item["store"],
            "rows": [int(index) for index in matching],
            "category_a": str(frame.at[matching[0], "品类A"] or ""),
            "category_b": str(frame.at[matching[0], "品类B"] or ""),
        }
    )
    for index in matching:
        frame.at[index, "Listing"] = item["listing"]
        frame.at[index, "品类A"] = item["category_a"]
        frame.at[index, "品类B"] = item["category_b"]
        if "产品名称" in frame.columns and item["product_name"]:
            frame.at[index, "产品名称"] = item["product_name"]


def append_category_row(frame: pd.DataFrame, item: dict[str, str]) -> None:
    new_row: dict[str, Any] = {column: "" for column in frame.columns}
    new_row.update(
        {
            "MSKU": item["msku"],
            "店铺/站点": item["store"],
            "Listing": item["listing"],
            "品类A": item["category_a"],
            "品类B": item["category_b"],
        }
    )
    if "产品名称" in frame.columns:
        new_row["产品名称"] = item["product_name"]
    frame.loc[len(frame), list(new_row)] = list(new_row.values())
