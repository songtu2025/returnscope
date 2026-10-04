from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from return_semantics.schemas import (
    CategoryDefinition,
    ClaimEvidenceRequirement,
    DimensionContract,
    EvidenceRequirement,
    ImplicitEvidenceRule,
    LabelDefinition,
    TaxonomyConfig,
    TaxonomyValidationRules,
)


@dataclass(frozen=True)
class CategoryVariant:
    category_a: str
    category_b: str
    attributes: dict[str, str]


@dataclass(frozen=True)
class ModelPolicy:
    version: str
    first_pass_role: str
    review_role: str | None


@dataclass(frozen=True)
class CategoryCapability:
    key: str
    agent_family: str
    logic_version: str
    model_policy: ModelPolicy
    variants: tuple[CategoryVariant, ...]
    taxonomy_path: Path | None = None
    taxonomy: TaxonomyConfig | None = None


@dataclass
class _CombinedTaxonomy:
    version: str
    hierarchical: bool
    categories: list[CategoryDefinition] = field(default_factory=list)
    hierarchy_labels: set[str] = field(default_factory=set)
    neutral_reason_labels: list[str] = field(default_factory=list)
    required_review_labels: list[str] = field(default_factory=list)
    fallback_label_codes: list[str] = field(default_factory=list)
    group_sets: list[list[str]] = field(default_factory=list)
    conflict_scopes: list[str] = field(default_factory=list)
    labels: dict[str, LabelDefinition] = field(default_factory=dict)
    parts: list[str] = field(default_factory=list)
    opposite_reason_labels: dict[str, list[str]] = field(default_factory=dict)
    conflicting_label_sets: list[list[str]] = field(default_factory=list)
    evidence_requirements: list[EvidenceRequirement] = field(default_factory=list)
    implicit_evidence_rules: list[ImplicitEvidenceRule] = field(default_factory=list)
    claim_evidence_requirements: list[ClaimEvidenceRequirement] = field(
        default_factory=list
    )
    dimension_contracts: list[DimensionContract] = field(default_factory=list)

    def build(self) -> TaxonomyConfig:
        return TaxonomyConfig(
            version=self.version,
            structure_version=2 if self.hierarchical else 1,
            categories=self.categories,
            agent_family="multi-category",
            product_context="多品类商品",
            allowed_parts=self.parts,
            instructions=[],
            validation_rules=TaxonomyValidationRules(
                neutral_reason_labels=list(dict.fromkeys(self.neutral_reason_labels)),
                required_review_labels=list(dict.fromkeys(self.required_review_labels)),
                fallback_label_codes=list(dict.fromkeys(self.fallback_label_codes)),
                allowed_groups=self.group_sets[0] if all(self.group_sets) else [],
                conflict_scope=(
                    "evidence"
                    if all(scope == "evidence" for scope in self.conflict_scopes)
                    else "comment"
                ),
                opposite_reason_labels=self.opposite_reason_labels,
                conflicting_label_sets=self.conflicting_label_sets,
                evidence_requirements=self.evidence_requirements,
                implicit_evidence_rules=self.implicit_evidence_rules,
                claim_evidence_requirements=self.claim_evidence_requirements,
                dimension_contracts=self.dimension_contracts,
            ),
            labels=list(self.labels.values()),
        )


def resolve_model_policy(
    capability: CategoryCapability,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    primary = {
        "role": "primary",
        "model": str(config["primary_model"]),
        "effort": str(config["primary_effort"]),
    }

    def resolve_role(role: str) -> dict[str, str]:
        if role == "primary":
            return dict(primary)
        model = config.get(f"{role}_model")
        effort = config.get(f"{role}_effort")
        if model:
            return {
                "role": role,
                "model": str(model),
                "effort": str(effort or config["primary_effort"]),
            }
        return {**primary, "fallback_from": role}

    review = (
        resolve_role(capability.model_policy.review_role)
        if capability.model_policy.review_role
        else None
    )
    return {
        "version": capability.model_policy.version,
        "configured": {
            "first_pass_role": capability.model_policy.first_pass_role,
            "review_role": capability.model_policy.review_role,
        },
        "actual": {
            "primary": primary,
            "first_pass": resolve_role(capability.model_policy.first_pass_role),
            "review": review,
        },
    }


def _parse_capabilities(
    data: Mapping[str, Any], base_dir: Path
) -> list[CategoryCapability]:
    capabilities = []
    for item in data["families"]:
        policy_data = item["model_policy"]
        first_pass_role = str(policy_data["first_pass_role"])
        review_role = policy_data.get("review_role")
        if first_pass_role not in {"cheap", "primary"}:
            raise ValueError(f"不支持的首轮模型角色: {first_pass_role}")
        if review_role not in {None, "primary", "secondary"}:
            raise ValueError(f"不支持的复核模型角色: {review_role}")
        variants = tuple(
            CategoryVariant(
                category_a=str(variant["category_a"]).strip(),
                category_b=str(variant["category_b"]).strip(),
                attributes={
                    str(key): str(value)
                    for key, value in variant.get("attributes", {}).items()
                },
            )
            for variant in item["variants"]
        )
        capabilities.append(
            CategoryCapability(
                key=str(item["key"]),
                agent_family=str(item["agent_family"]),
                logic_version=str(item["logic_version"]),
                taxonomy_path=base_dir / str(item["taxonomy"]),
                model_policy=ModelPolicy(
                    version=str(policy_data["version"]),
                    first_pass_role=first_pass_role,
                    review_role=(str(review_role) if review_role else None),
                ),
                variants=variants,
            )
        )
    return capabilities
