from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from return_semantics.capabilities import (
    CapabilityRegistry,
    CategoryCapability,
    resolve_model_policy,
)
from return_semantics.claims import NO_CLAIMS_VERSION, ClaimsResolver
from return_semantics.data import ReturnDataset
from return_semantics.execution_plan_summary import (
    _product_match_statuses as _product_match_statuses,
)
from return_semantics.execution_plan_summary import _variant_counts as _variant_counts
from return_semantics.execution_plan_summary import (
    build_plan_summary,
    prepare_plan_groups,
)


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
            output.setdefault(assignment, []).append(str(row.classification_key))
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


def _scope_segment_key(store: str, listing: str, agent_key: str) -> str:
    return f"{store}/{listing or '*'}/{agent_key}"


class _CategoryPlanBuilder:
    def __init__(
        self,
        dataset: ReturnDataset,
        registry: CapabilityRegistry,
        scope: tuple[str, str | None],
        model_config: dict[str, Any],
        claims_resolver: ClaimsResolver | None,
    ) -> None:
        self.dataset = dataset
        self.registry = registry
        self.store, self.listing = scope
        self.model_config = model_config
        self.claims_resolver = claims_resolver
        self.unique_comments = dataset.unique_comments
        self.record_counts = dataset.records["classification_key"].value_counts()
        self.split_scopes = dataset.scope_mode == "auto"
        self.assignments = self._assignments()
        self.assignment_series = pd.Series(
            self.assignments, index=self.unique_comments.index
        )
        self.groups = prepare_plan_groups(
            self.unique_comments, self.assignment_series, self.record_counts
        )

    def _assignments(self) -> tuple[str | None, ...]:
        assignments_list: list[str | None] = []
        for row in self.unique_comments.itertuples(index=False):
            category_a = str(row.category_a).strip()
            category_b = str(row.category_b).strip()
            row_match_status = str(
                getattr(row, "product_match_status", "matched")
            ).strip()
            if row_match_status != "matched":
                assignments_list.append("excluded")
                continue
            if not category_a or not category_b:
                assignments_list.append("excluded")
                continue
            capability = self.registry.resolve(category_a, category_b)
            if capability is None or (self.split_scopes and (not str(row.store))):
                assignments_list.append(None)
                continue
            assignments_list.append(
                _scope_segment_key(str(row.store), str(row.listing), capability.key)
                if self.split_scopes
                else capability.key
            )
        return tuple(assignments_list)

    def _segments(self) -> list[dict[str, Any]]:
        segments: list[dict[str, Any]] = []
        for capability in self.registry.capabilities:
            if self.split_scopes:
                scope_groups: Iterable[tuple[tuple[Any, Any], pd.DataFrame]] = (
                    self.unique_comments.groupby(
                        ["store", "listing"], sort=True, dropna=False
                    )
                )
            else:
                scope_groups = [
                    ((self.store, self.listing or ""), self.unique_comments)
                ]
            for (scope_store, scope_listing), scope_rows in scope_groups:
                segment_key = (
                    _scope_segment_key(
                        str(scope_store), str(scope_listing), capability.key
                    )
                    if self.split_scopes
                    else capability.key
                )
                selected = scope_rows.loc[self.assignment_series.eq(segment_key)].copy()
                if selected.empty:
                    continue
                segments.append(
                    self._build_segment(
                        capability, (scope_store, scope_listing), segment_key, selected
                    )
                )
        return segments

    def _build_segment(
        self,
        capability: CategoryCapability,
        scope: tuple[Any, Any],
        segment_key: str,
        selected: pd.DataFrame,
    ) -> dict[str, Any]:
        scope_store, scope_listing = scope
        taxonomy = self.registry.load_taxonomy(capability)
        model_policy = resolve_model_policy(capability, self.model_config)
        claims = (
            self.claims_resolver.resolve(
                str(scope_store), str(scope_listing) or None, capability.key
            )
            if self.claims_resolver is not None
            else None
        )
        return {
            "segment_key": segment_key,
            "agent_key": capability.key,
            "agent_family": capability.agent_family,
            "logic_version": capability.logic_version,
            "taxonomy_version": taxonomy.version,
            "model_policy_version": capability.model_policy.version,
            "model_policy": model_policy,
            "claims_version": claims.version
            if claims is not None
            else NO_CLAIMS_VERSION,
            "scope": {"store": str(scope_store), "listing": str(scope_listing)},
            "record_count": int(
                selected["classification_key"].map(self.record_counts).fillna(0).sum()
            ),
            "unique_comments": len(selected),
            "status": "ready",
            "variants": _variant_counts(selected, self.record_counts),
        }

    def summary(self) -> dict[str, Any]:
        return build_plan_summary(
            self.dataset, self.registry, self.groups, self._segments(), self.store
        )


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
    builder = _CategoryPlanBuilder(
        dataset, registry, (store, listing), effective_model_config, claims_resolver
    )
    return CategoryExecutionPlan(
        summary=builder.summary(), assignments=builder.assignments
    )


# 辅助入口仍从原模块导出，并共享统计模块的唯一实现。
_variant_counts.__module__ = __name__
_product_match_statuses.__module__ = __name__
