from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import pandas as pd

from return_semantics.capabilities import (
    CapabilityRegistry,
    resolve_model_policy,
)
from return_semantics.claims import NO_CLAIMS_VERSION, ClaimsResolver
from return_semantics.data import ReturnDataset


@dataclass(frozen=True)
class CategoryExecutionPlan:
    summary: dict[str, Any]
    assignments: tuple[str | None, ...]

    def with_hash(self, context: dict[str, Any]) -> dict[str, Any]:
        payload = {"context": context, "plan": self.summary}
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return {
            **self.summary,
            "plan_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        }

    def classification_keys_by_segment(
        self,
        dataset: ReturnDataset,
    ) -> dict[str, list[str]]:
        output: dict[str, list[str]] = {}
        for assignment, row in zip(
            self.assignments,
            dataset.unique_comments.itertuples(index=False),
            strict=True,
        ):
            if assignment in {None, "excluded"}:
                continue
            output.setdefault(assignment, []).append(
                str(row.classification_key)
            )
        return output

    def unresolved_classification_keys(
        self,
        dataset: ReturnDataset,
    ) -> list[str]:
        return [
            str(row.classification_key)
            for assignment, row in zip(
                self.assignments,
                dataset.unique_comments.itertuples(index=False),
                strict=True,
            )
            if assignment is None
        ]


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


def _scope_segment_key(store: str, listing: str, agent_key: str) -> str:
    return f"{store}/{listing or '*'}/{agent_key}"


def build_category_execution_plan(
    dataset: ReturnDataset,
    registry: CapabilityRegistry,
    *,
    store: str = "",
    listing: str | None = None,
    model_config: dict[str, Any] | None = None,
    claims_resolver: ClaimsResolver | None = None,
) -> CategoryExecutionPlan:
    effective_model_config = model_config or {
        "primary_model": "primary",
        "primary_effort": "medium",
        "cheap_model": None,
        "cheap_effort": None,
        "secondary_model": None,
        "secondary_effort": None,
    }
    unique_comments = dataset.unique_comments
    record_counts = dataset.records["classification_key"].value_counts()
    split_scopes = dataset.scope_mode == "auto"
    assignments_list: list[str | None] = []
    for row in unique_comments.itertuples(index=False):
        category_a = str(row.category_a).strip()
        category_b = str(row.category_b).strip()
        match_status = str(
            getattr(row, "product_match_status", "matched")
        ).strip()
        if match_status != "matched":
            assignments_list.append("excluded")
            continue
        if not category_a or not category_b:
            assignments_list.append("excluded")
            continue
        capability = registry.resolve(
            category_a,
            category_b,
        )
        if capability is None or (split_scopes and not str(row.store)):
            assignments_list.append(None)
            continue
        assignments_list.append(
            _scope_segment_key(str(row.store), str(row.listing), capability.key)
            if split_scopes
            else capability.key
        )
    assignments = tuple(assignments_list)
    assignment_series = pd.Series(assignments, index=unique_comments.index)
    segments: list[dict[str, Any]] = []

    excluded = unique_comments.loc[assignment_series.eq("excluded")].copy()
    blocked = unique_comments.loc[assignment_series.isna()].copy()
    match_status = (
        unique_comments["product_match_status"].fillna("").astype(str).str.strip()
        if "product_match_status" in unique_comments.columns
        else pd.Series("matched", index=unique_comments.index)
    )
    unmatched_product = unique_comments.loc[match_status.ne("matched")].copy()
    missing_category = unique_comments.loc[
        match_status.eq("matched")
        & (
            unique_comments["category_a"].fillna("").astype(str).str.strip().eq("")
            | unique_comments["category_b"].fillna("").astype(str).str.strip().eq("")
        )
    ].copy()
    for capability in registry.capabilities:
        if split_scopes:
            scope_groups = unique_comments.groupby(
                ["store", "listing"],
                sort=True,
                dropna=False,
            )
        else:
            scope_groups = [((store, listing or ""), unique_comments)]
        for (scope_store, scope_listing), scope_rows in scope_groups:
            segment_key = (
                _scope_segment_key(
                    str(scope_store),
                    str(scope_listing),
                    capability.key,
                )
                if split_scopes
                else capability.key
            )
            selected = scope_rows.loc[assignment_series.eq(segment_key)].copy()
            if selected.empty:
                continue
            taxonomy = registry.load_taxonomy(capability)
            model_policy = resolve_model_policy(
                capability,
                effective_model_config,
            )
            claims = (
                claims_resolver.resolve(
                    str(scope_store),
                    str(scope_listing) or None,
                    capability.key,
                )
                if claims_resolver is not None
                else None
            )
            segments.append(
                {
                    "segment_key": segment_key,
                    "agent_key": capability.key,
                    "agent_family": capability.agent_family,
                    "logic_version": capability.logic_version,
                    "taxonomy_version": taxonomy.version,
                    "model_policy_version": capability.model_policy.version,
                    "model_policy": model_policy,
                    "claims_version": (
                        claims.version if claims is not None else NO_CLAIMS_VERSION
                    ),
                    "scope": {
                        "store": str(scope_store),
                        "listing": str(scope_listing),
                    },
                    "record_count": int(
                        selected["classification_key"]
                        .map(record_counts)
                        .fillna(0)
                        .sum()
                    ),
                    "unique_comments": len(selected),
                    "status": "ready",
                    "variants": _variant_counts(selected, record_counts),
                }
            )

    unsupported = blocked.loc[
        [
            registry.resolve(str(row.category_a), str(row.category_b)) is None
            for row in blocked.itertuples(index=False)
        ]
    ]
    unresolved_scope = blocked.drop(index=unsupported.index)
    executable = sum(
        int(segment["unique_comments"])
        for segment in segments
        if segment["status"] == "ready"
    )
    executable_records = sum(
        int(segment["record_count"])
        for segment in segments
        if segment["status"] == "ready"
    )
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
    summary = {
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
            unresolved_scope.loc[
                unresolved_scope["store"].eq(""),
                "classification_key",
            ]
            .map(record_counts)
            .fillna(0)
            .sum()
            if "store" in unresolved_scope.columns
            else 0
        ),
        "record_count": len(dataset.records),
        "valid_comment_count": valid_comment_count,
        "unique_comment_count": len(unique_comments),
        "executable_count": executable,
        "executable_record_count": executable_records,
        "blocked_count": len(blocked),
        "blocked_record_count": blocked_records,
        "excluded_count": len(not_analyzed),
        "excluded_record_count": excluded_records,
        "excluded_categories": _variant_counts(not_analyzed, record_counts),
        "unmatched_product_count": len(unmatched_product),
        "unmatched_product_record_count": int(
            unmatched_product["classification_key"]
            .map(record_counts)
            .fillna(0)
            .sum()
        ),
        "missing_category_count": len(missing_category),
        "missing_category_record_count": int(
            missing_category["classification_key"]
            .map(record_counts)
            .fillna(0)
            .sum()
        ),
        "missing_categories": _variant_counts(missing_category, record_counts),
        "unknown_category_count": len(unsupported),
        "unknown_category_record_count": int(
            unsupported["classification_key"].map(record_counts).fillna(0).sum()
        ),
        "unknown_categories": _variant_counts(unsupported, record_counts),
        "segments": segments,
    }
    return CategoryExecutionPlan(summary=summary, assignments=assignments)
