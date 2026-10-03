from __future__ import annotations

from pathlib import Path
from typing import Any

from return_semantics.data import ReturnDataset, load_product_dimensions
from return_semantics.task_plan import (
    CategoryExecutionPlan,
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

    def _unresolved_products(
        self,
        dataset: ReturnDataset,
        execution_plan: CategoryExecutionPlan,
        product_path: Path,
        store: str,
        listing: str | None,
    ) -> list[dict[str, Any]]:
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
        resolution_keys = unresolved_keys | missing_category_keys
        if not resolution_keys:
            return []
        blocked = dataset.records.loc[
            dataset.records["has_text_evidence"]
            & dataset.records["classification_key"].isin(resolution_keys)
        ].copy()
        fallback_store = "" if store == "AUTO" else store
        context_by_store: dict[
            str,
            tuple[frozenset[str], list[str], dict[str, str]],
        ] = {}

        def store_context(
            scope_store: str,
        ) -> tuple[
            frozenset[str],
            list[str],
            dict[str, str],
        ]:
            if not scope_store:
                return frozenset(), [], {}
            if scope_store not in context_by_store:
                scope_listing = listing if dataset.scope_mode == "manual" else None
                dimensions = load_product_dimensions(
                    product_path,
                    scope_store,
                    scope_listing,
                )
                listings = sorted(
                    value for value in dimensions["Listing"].unique().tolist() if value
                )
                listing_by_msku = (
                    dimensions.loc[
                        dimensions["MSKU"].ne(""),
                        ["MSKU", "Listing"],
                    ]
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

        output = []
        for (row_store, sku), rows in blocked.groupby(
            ["store", "sku"],
            sort=True,
            dropna=False,
        ):
            scope_store = str(row_store).strip() or fallback_store
            clean_sku = str(sku).strip()
            store_mskus, listings, listing_by_msku = store_context(scope_store)
            category_a = str(rows["category_a"].iloc[0]).strip()
            category_b = str(rows["category_b"].iloc[0]).strip()
            product_names = [
                str(value).strip()
                for value in rows["product_name"].tolist()
                if str(value).strip().lower() not in {"", "nan", "none"}
            ]
            existing = clean_sku in store_mskus
            if not clean_sku:
                issue = "missing_product_key"
            elif existing and not category_a and not category_b:
                issue = "missing_category"
            elif existing:
                issue = "unsupported_category"
            else:
                issue = "product_not_found"
            suggested_listing = str(
                listing_by_msku.get(clean_sku)
                or self._suggest_listing(clean_sku, listings)
            )
            item = {
                "product_key": (
                    f"{scope_store}/{clean_sku}"
                    if dataset.scope_mode == "auto" and scope_store
                    else clean_sku
                ),
                "store": scope_store,
                "msku": clean_sku,
                "product_name": product_names[0] if product_names else "",
                "current_category_a": category_a,
                "current_category_b": category_b,
                "suggested_listing": suggested_listing,
                "record_count": len(rows),
                "comment_count": int(rows["classification_key"].nunique()),
                "issue": issue,
                "existing_product": existing,
                "editable": bool(scope_store and clean_sku),
            }
            output.append(item)
        return sorted(
            output,
            key=lambda item: (
                -int(item["comment_count"]),
                -int(item["record_count"]),
                str(item["store"]),
                str(item["msku"]),
            ),
        )
