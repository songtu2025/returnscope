from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from return_semantics.capabilities import CapabilityRegistry
from return_semantics.data import ReturnDataset


@dataclass(frozen=True)
class _PlanGroups:
    record_counts: pd.Series
    excluded: pd.DataFrame
    blocked: pd.DataFrame
    unmatched_product: pd.DataFrame
    missing_category: pd.DataFrame


def _variant_counts(
    selected: pd.DataFrame,
    record_counts: pd.Series,
) -> list[dict[str, Any]]:
    variants = []
    for (category_a, category_b), rows in selected.groupby(
        ["category_a", "category_b"],
        sort=True,
        dropna=False,
    ):
        variants.append(
            {
                "category_a": str(category_a),
                "category_b": str(category_b),
                "record_count": int(
                    rows["classification_key"].map(record_counts).fillna(0).sum()
                ),
                "unique_comments": len(rows),
            }
        )
    return variants


def _product_match_statuses(unique_comments: pd.DataFrame) -> pd.Series:
    if "product_match_status" not in unique_comments.columns:
        return pd.Series("matched", index=unique_comments.index)
    values = unique_comments["product_match_status"]
    if not isinstance(values, pd.Series):
        raise ValueError("product_match_status 列必须唯一")
    return values.fillna("").astype(str).str.strip()


def prepare_plan_groups(
    unique_comments: pd.DataFrame,
    assignment_series: pd.Series,
    record_counts: pd.Series,
) -> _PlanGroups:
    excluded = unique_comments.loc[assignment_series.eq("excluded")].copy()
    blocked = unique_comments.loc[assignment_series.isna()].copy()
    match_status = _product_match_statuses(unique_comments)
    unmatched_product = unique_comments.loc[match_status.ne("matched")].copy()
    missing_category = unique_comments.loc[
        match_status.eq("matched")
        & (
            unique_comments["category_a"].fillna("").astype(str).str.strip().eq("")
            | unique_comments["category_b"].fillna("").astype(str).str.strip().eq("")
        )
    ].copy()
    return _PlanGroups(
        record_counts, excluded, blocked, unmatched_product, missing_category
    )


def _scope_summary(
    dataset: ReturnDataset,
    registry: CapabilityRegistry,
    store: str,
    unresolved_scope: pd.DataFrame,
    record_counts: pd.Series,
) -> dict[str, Any]:
    return {
        "registry_version": registry.version,
        "scope_mode": dataset.scope_mode,
        "primary_store": dataset.primary_store or store,
        "detected_scopes": list(dataset.scopes),
        "unresolved_scope_count": int(
            unresolved_scope["store"].eq("").sum()
            if "store" in unresolved_scope.columns
            else 0
        ),
        "unresolved_scope_record_count": int(
            unresolved_scope.loc[unresolved_scope["store"].eq(""), "classification_key"]
            .map(record_counts)
            .fillna(0)
            .sum()
            if "store" in unresolved_scope.columns
            else 0
        ),
    }


def _execution_counts(segments: list[dict[str, Any]]) -> tuple[int, int]:
    executable = sum(
        (
            int(segment["unique_comments"])
            for segment in segments
            if segment["status"] == "ready"
        )
    )
    executable_records = sum(
        (
            int(segment["record_count"])
            for segment in segments
            if segment["status"] == "ready"
        )
    )
    return (executable, executable_records)


def _excluded_summary(
    groups: _PlanGroups,
    unsupported: pd.DataFrame,
    not_analyzed: pd.DataFrame,
    excluded_records: int,
    blocked_records: int,
) -> dict[str, Any]:
    record_counts = groups.record_counts
    blocked = groups.blocked
    unmatched_product = groups.unmatched_product
    missing_category = groups.missing_category
    return {
        "blocked_count": len(blocked),
        "blocked_record_count": blocked_records,
        "excluded_count": len(not_analyzed),
        "excluded_record_count": excluded_records,
        "excluded_categories": _variant_counts(not_analyzed, record_counts),
        "unmatched_product_count": len(unmatched_product),
        "unmatched_product_record_count": int(
            unmatched_product["classification_key"].map(record_counts).fillna(0).sum()
        ),
        "missing_category_count": len(missing_category),
        "missing_category_record_count": int(
            missing_category["classification_key"].map(record_counts).fillna(0).sum()
        ),
        "missing_categories": _variant_counts(missing_category, record_counts),
        "unknown_category_count": len(unsupported),
        "unknown_category_record_count": int(
            unsupported["classification_key"].map(record_counts).fillna(0).sum()
        ),
        "unknown_categories": _variant_counts(unsupported, record_counts),
    }


def build_plan_summary(
    dataset: ReturnDataset,
    registry: CapabilityRegistry,
    groups: _PlanGroups,
    segments: list[dict[str, Any]],
    store: str,
) -> dict[str, Any]:
    unique_comments = dataset.unique_comments
    record_counts = groups.record_counts
    excluded = groups.excluded
    blocked = groups.blocked
    unsupported = blocked.loc[
        [
            registry.resolve(str(row.category_a), str(row.category_b)) is None
            for row in blocked.itertuples(index=False)
        ]
    ]
    unresolved_scope = blocked.drop(index=unsupported.index)
    executable, executable_records = _execution_counts(segments)
    not_analyzed = pd.concat([excluded, blocked]).sort_index()
    excluded_records = int(
        not_analyzed["classification_key"].map(record_counts).fillna(0).sum()
    )
    blocked_records = int(
        blocked["classification_key"].map(record_counts).fillna(0).sum()
    )
    valid_comment_count = (
        int(dataset.records["has_text_evidence"].sum())
        if "has_text_evidence" in dataset.records.columns
        else len(dataset.records)
    )
    return {
        **_scope_summary(dataset, registry, store, unresolved_scope, record_counts),
        **{
            "record_count": len(dataset.records),
            "valid_comment_count": valid_comment_count,
            "unique_comment_count": len(unique_comments),
            "executable_count": executable,
            "executable_record_count": executable_records,
        },
        **_excluded_summary(
            groups, unsupported, not_analyzed, excluded_records, blocked_records
        ),
        "segments": segments,
    }
