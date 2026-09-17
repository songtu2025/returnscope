from __future__ import annotations

import json
from collections.abc import Iterable
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
from return_semantics.taxonomy import load_taxonomy


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


class CapabilityRegistry:
    def __init__(
        self,
        version: str,
        capabilities: tuple[CategoryCapability, ...],
    ) -> None:
        self.version = version
        self.capabilities = capabilities
        self._variants: dict[tuple[str, str], CategoryCapability] = {}
        for capability in capabilities:
            for variant in capability.variants:
                key = (variant.category_a, variant.category_b)
                if key in self._variants:
                    raise ValueError(
                        f"品类映射重复: {variant.category_a}/{variant.category_b}"
                    )
                self._variants[key] = capability

    def resolve(
        self,
        category_a: str,
        category_b: str,
    ) -> CategoryCapability | None:
        return self._variants.get((category_a.strip(), category_b.strip()))

    def variant(
        self,
        category_a: str,
        category_b: str,
    ) -> CategoryVariant | None:
        capability = self.resolve(category_a, category_b)
        if capability is None:
            return None
        target = (category_a.strip(), category_b.strip())
        return next(
            (
                item
                for item in capability.variants
                if (item.category_a, item.category_b) == target
            ),
            None,
        )

    def load_taxonomy(self, capability: CategoryCapability) -> TaxonomyConfig:
        if capability.taxonomy is not None:
            return capability.taxonomy
        if capability.taxonomy_path is None:
            raise ValueError(f"分类能力 {capability.key} 缺少标签体系")
        return load_taxonomy(capability.taxonomy_path)

    def combined_taxonomy(self) -> TaxonomyConfig:
        taxonomies = [self.load_taxonomy(item) for item in self.capabilities]
        hierarchical = any(item.structure_version == 2 for item in taxonomies)
        combined = _CombinedTaxonomy(self.version, hierarchical)
        for capability, taxonomy in zip(self.capabilities, taxonomies, strict=True):
            _merge_taxonomy(combined, capability.key, taxonomy)
        return combined.build()

    @staticmethod
    def _merge_shared_label(
        existing: LabelDefinition,
        incoming: LabelDefinition,
    ) -> LabelDefinition:
        existing_semantics = (
            existing.name,
            existing.group,
            existing.description,
            frozenset(existing.allowed_sentiments),
        )
        incoming_semantics = (
            incoming.name,
            incoming.group,
            incoming.description,
            frozenset(incoming.allowed_sentiments),
        )
        if existing_semantics != incoming_semantics:
            raise ValueError(f"跨品类标签编码语义冲突: {existing.code}")
        return existing.model_copy(
            update={
                "keywords": list(
                    dict.fromkeys([*existing.keywords, *incoming.keywords])
                ),
                "exclusions": list(
                    dict.fromkeys([*existing.exclusions, *incoming.exclusions])
                ),
                "examples": [
                    *existing.examples,
                    *[
                        example
                        for example in incoming.examples
                        if example not in existing.examples
                    ],
                ],
                "allowed_claim_ids": list(
                    dict.fromkeys(
                        [*existing.allowed_claim_ids, *incoming.allowed_claim_ids]
                    )
                ),
            }
        )


def _merge_taxonomy(
    combined: _CombinedTaxonomy,
    capability_key: str,
    taxonomy: TaxonomyConfig,
) -> None:
    incoming_labels = taxonomy.labels
    if combined.hierarchical:
        categories, incoming_labels = _combined_tree(capability_key, taxonomy)
        combined.categories.extend(categories)
    for label in incoming_labels:
        _merge_label(combined, taxonomy, label)
    _extend_unique(combined.parts, taxonomy.allowed_parts)
    _merge_validation_rules(combined, capability_key, taxonomy)


def _merge_label(
    combined: _CombinedTaxonomy,
    taxonomy: TaxonomyConfig,
    label: LabelDefinition,
) -> None:
    existing = combined.labels.get(label.code)
    if existing is None:
        combined.labels[label.code] = label
    elif taxonomy.structure_version == 2 or label.code in combined.hierarchy_labels:
        raise ValueError(f"不同框架的末端编码重复，不能自动合并: {label.code}")
    else:
        combined.labels[label.code] = CapabilityRegistry._merge_shared_label(
            existing, label
        )
    if taxonomy.structure_version == 2:
        combined.hierarchy_labels.add(label.code)


def _merge_validation_rules(
    combined: _CombinedTaxonomy,
    capability_key: str,
    taxonomy: TaxonomyConfig,
) -> None:
    rules = taxonomy.validation_rules
    combined.group_sets.append(rules.allowed_groups)
    combined.conflict_scopes.append(rules.conflict_scope)
    neutral_codes = rules.neutral_reason_labels
    if neutral_codes is None:
        neutral_codes = [
            label.code
            for label in taxonomy.labels
            if label.group in {"其他", "其他原因"}
        ]
    combined.neutral_reason_labels.extend(neutral_codes)
    combined.required_review_labels.extend(rules.required_review_labels)
    combined.fallback_label_codes.extend(rules.fallback_label_codes)
    _merge_code_map(combined.opposite_reason_labels, rules.opposite_reason_labels)
    _extend_unique(combined.conflicting_label_sets, rules.conflicting_label_sets)
    _extend_unique(combined.evidence_requirements, rules.evidence_requirements)
    _extend_unique(combined.implicit_evidence_rules, rules.implicit_evidence_rules)
    _extend_unique(
        combined.claim_evidence_requirements,
        rules.claim_evidence_requirements,
    )
    _extend_unique(
        combined.dimension_contracts,
        [
            rule.model_copy(
                update={"parent_code": f"{capability_key}::{rule.parent_code}"}
            )
            for rule in rules.dimension_contracts
        ],
    )


def _merge_code_map(
    target: dict[str, list[str]],
    source: dict[str, list[str]],
) -> None:
    for reason, codes in source.items():
        _extend_unique(target.setdefault(reason, []), codes)


def _extend_unique(target: list[Any], values: Iterable[Any]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _combined_tree(
    capability_key: str, taxonomy: TaxonomyConfig
) -> tuple[list[CategoryDefinition], list[LabelDefinition]]:
    """组合视图按能力隔离分类节点，不改变源版本中的编码和关系。"""
    prefix = f"{capability_key}::"
    if taxonomy.structure_version == 2:
        categories = [
            category.model_copy(
                update={
                    "code": prefix + category.code,
                    "parent_code": prefix + category.parent_code
                    if category.parent_code is not None
                    else None,
                }
            )
            for category in taxonomy.categories
        ]
        labels = [
            label.model_copy(update={"parent_code": prefix + str(label.parent_code)})
            for label in taxonomy.labels
        ]
    else:
        groups = list(dict.fromkeys(label.group for label in taxonomy.labels))
        categories = [
            CategoryDefinition(code=prefix + group, name=group) for group in groups
        ]
        labels = [
            label.model_copy(update={"parent_code": prefix + label.group})
            for label in taxonomy.labels
        ]
    return categories, labels


def load_capability_registry(path: Path) -> CapabilityRegistry:
    data = json.loads(path.read_text(encoding="utf-8"))
    base_dir = path.parent
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
    return CapabilityRegistry(
        version=str(data["version"]),
        capabilities=tuple(capabilities),
    )
