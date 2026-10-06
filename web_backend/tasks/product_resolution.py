from __future__ import annotations

from pathlib import Path
from typing import Any

from pandas import DataFrame

from return_semantics.data import ReturnDataset, load_product_dimensions
from return_semantics.task_plan import CategoryExecutionPlan

_ProductContext = tuple[frozenset[str], list[str], dict[str, str]]


def _resolution_keys(
    dataset: ReturnDataset, execution_plan: CategoryExecutionPlan
) -> set[str]:
    unresolved_keys = set(execution_plan.unresolved_classification_keys(dataset))
    missing_category_keys = {
        str(row.classification_key)
        for assignment, row in zip(
            execution_plan.assignments,
            dataset.unique_comments.itertuples(index=False),
            strict=True,
        )
        if assignment == "excluded"
    }
    return unresolved_keys | missing_category_keys


def _product_context(
    scope_store: str,
    product_path: Path,
    scope_listing: str | None,
    context_by_store: dict[str, _ProductContext],
) -> _ProductContext:
    if not scope_store:
        return frozenset(), [], {}
    if scope_store not in context_by_store:
        dimensions = load_product_dimensions(product_path, scope_store, scope_listing)
        listings = sorted(
            value for value in dimensions["Listing"].unique().tolist() if value
        )
        listing_by_msku = (
            dimensions.loc[dimensions["MSKU"].ne(""), ["MSKU", "Listing"]]
            .drop_duplicates(subset=["MSKU"])
            .set_index("MSKU")["Listing"]
            .to_dict()
        )
        context_by_store[scope_store] = (
            frozenset(dimensions["MSKU"]),
            listings,
            listing_by_msku,
        )
    return context_by_store[scope_store]


def _product_issue(sku: str, existing: bool, category_a: str, category_b: str) -> str:
    if not sku:
        return "missing_product_key"
    if existing and not category_a and not category_b:
        return "missing_category"
    if existing:
        return "unsupported_category"
    return "product_not_found"


def _resolution_sort_key(item: dict[str, Any]) -> tuple[int, int, str, str]:
    return (
        -int(item["comment_count"]),
        -int(item["record_count"]),
        str(item["store"]),
        str(item["msku"]),
    )


class TaskProductResolutionMixin:
    @staticmethod
    def _suggest_listing(sku: str, listings: list[str]) -> str:
        candidates = [
            value
            for value in listings
            if sku == value
            or sku.startswith(f"{value}-")
            or sku.startswith(f"{value}_")
            or sku.startswith(f"{value} ")
        ]
        return max(candidates, key=len) if candidates else ""

    def _resolution_record(
        self,
        rows: DataFrame,
        sku: str,
        store: str,
        scope_mode: str,
        context: _ProductContext,
    ) -> dict[str, Any]:
        store_mskus, listings, listing_by_msku = context
        category_a = str(rows["category_a"].iloc[0]).strip()
        category_b = str(rows["category_b"].iloc[0]).strip()
        product_names = [
            str(value).strip()
            for value in rows["product_name"].tolist()
            if str(value).strip().lower() not in {"", "nan", "none"}
        ]
        existing = sku in store_mskus
        suggested_listing = str(
            listing_by_msku.get(sku) or self._suggest_listing(sku, listings)
        )
        return {
            "product_key": f"{store}/{sku}" if scope_mode == "auto" and store else sku,
            "store": store,
            "msku": sku,
            "product_name": product_names[0] if product_names else "",
            "current_category_a": category_a,
            "current_category_b": category_b,
            "suggested_listing": suggested_listing,
            "record_count": len(rows),
            "comment_count": int(rows["classification_key"].nunique()),
            "issue": _product_issue(sku, existing, category_a, category_b),
            "existing_product": existing,
            "editable": bool(store and sku),
        }

    def _unresolved_products(
        self,
        dataset: ReturnDataset,
        execution_plan: CategoryExecutionPlan,
        product_path: Path,
        store: str,
        listing: str | None,
    ) -> list[dict[str, Any]]:
        resolution_keys = _resolution_keys(dataset, execution_plan)
        if not resolution_keys:
            return []
        blocked = dataset.records.loc[
            dataset.records["has_text_evidence"]
            & dataset.records["classification_key"].isin(resolution_keys)
        ].copy()
        fallback_store = "" if store == "AUTO" else store
        context_by_store: dict[str, _ProductContext] = {}
        scope_listing = listing if dataset.scope_mode == "manual" else None
        output = []
        for (row_store, sku), rows in blocked.groupby(
            ["store", "sku"],
            sort=True,
            dropna=False,
        ):
            scope_store = str(row_store).strip() or fallback_store
            clean_sku = str(sku).strip()
            context = _product_context(
                scope_store, product_path, scope_listing, context_by_store
            )
            output.append(
                self._resolution_record(
                    rows, clean_sku, scope_store, dataset.scope_mode, context
                )
            )
        return sorted(output, key=_resolution_sort_key)
