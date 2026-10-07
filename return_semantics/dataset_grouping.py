from __future__ import annotations

import pandas as pd

from return_semantics.analysis_context import RETURNS_CONTEXT, AnalysisContext


def _assign_classification_keys(
    records: pd.DataFrame,
    scope_mode: str,
    analysis_context: AnalysisContext,
) -> None:
    records["classification_key"] = ""

    has_text = records["has_text_evidence"]
    category_scope = records["category_a"] + "\x1e" + records["category_b"]
    missing_category = records["category_a"].eq("") & records["category_b"].eq("")
    category_scope = category_scope.mask(
        missing_category,
        "SKU=" + records["sku"],
    )
    classification_scope = category_scope
    if scope_mode == "auto":
        classification_scope = (
            records["store"] + "\x1d" + records["listing"] + "\x1d" + category_scope
        )
    key_prefix = classification_scope.loc[has_text] + "\x1f"
    if analysis_context == RETURNS_CONTEXT:
        key_prefix += records.loc[has_text, "reason"] + "\x1f"
    records.loc[has_text, "classification_key"] = (
        key_prefix + records.loc[has_text, "comment_dedupe"]
    )


def _unique_comments(records: pd.DataFrame) -> pd.DataFrame:
    has_text = records["has_text_evidence"]
    unique_comments = (
        records.loc[
            has_text,
            [
                "classification_key",
                "reason",
                "feedback_title",
                "comment_normalized",
                "category_a",
                "category_b",
                "store",
                "listing",
                "product_match_status",
            ],
        ]
        .drop_duplicates(subset=["classification_key"])
        .reset_index(drop=True)
    )
    counts = records.loc[has_text, "classification_key"].value_counts()
    unique_comments["record_count"] = unique_comments["classification_key"].map(counts)
    return unique_comments


def _dataset_scopes(records: pd.DataFrame) -> tuple[dict[str, object], ...]:
    has_text = records["has_text_evidence"]
    scoped = records.loc[has_text & records["store"].ne("")]
    scopes = tuple(
        {
            "store": str(store),
            "listing": str(listing),
            "record_count": len(rows),
            "unique_comments": int(rows["classification_key"].nunique()),
        }
        for (store, listing), rows in scoped.groupby(
            ["store", "listing"],
            sort=True,
            dropna=False,
        )
    )
    return scopes
