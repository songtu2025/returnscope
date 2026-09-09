from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from return_semantics.schemas import (
    CategoryDefinition,
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
        categories: list[CategoryDefinition] = []
        hierarchy_labels: set[str] = set()
        neutral_reason_labels = []
        required_review_labels = []
        group_sets = []
        conflict_scopes = []
        labels: dict[str, LabelDefinition] = {}
        parts: list[str] = []
        opposite_reason_labels: dict[str, list[str]] = {}
        conflicting_label_sets: list[list[str]] = []
        evidence_requirements = []
        implicit_evidence_rules = []
        claim_evidence_requirements = []
        for capability, taxonomy in zip(self.capabilities, taxonomies, strict=True):
            incoming_labels = taxonomy.labels
            if hierarchical:
                new_categories, incoming_labels = _combined_tree(
                    capability.key, taxonomy
                )
                categories.extend(new_categories)
            for label in incoming_labels:
                existing = labels.get(label.code)
                if existing is None:
                    labels[label.code] = label
                else:
                    if (
                        taxonomy.structure_version == 2
                        or label.code in hierarchy_labels
                    ):
                        raise ValueError(
                            f"不同框架的末端编码重复，不能自动合并: {label.code}"
                        )
                    labels[label.code] = self._merge_shared_label(existing, label)
                if taxonomy.structure_version == 2:
                    hierarchy_labels.add(label.code)
            for part in taxonomy.allowed_parts:
                if part not in parts:
                    parts.append(part)
            rules = taxonomy.validation_rules
            group_sets.append(rules.allowed_groups)
            conflict_scopes.append(rules.conflict_scope)
            neutral_reason_labels.extend(
                rules.neutral_reason_labels
                if rules.neutral_reason_labels is not None
                else [
                    label.code
                    for label in taxonomy.labels
                    if label.group in {"其他", "其他原因"}
                ]
            )
            required_review_labels.extend(rules.required_review_labels)
            for reason, codes in rules.opposite_reason_labels.items():
                merged_codes = opposite_reason_labels.setdefault(reason, [])
                for code in codes:
                    if code not in merged_codes:
                        merged_codes.append(code)
            for codes in rules.conflicting_label_sets:
                if codes not in conflicting_label_sets:
                    conflicting_label_sets.append(codes)
            for rule in rules.evidence_requirements:
                if rule not in evidence_requirements:
                    evidence_requirements.append(rule)
            for rule in rules.implicit_evidence_rules:
                if rule not in implicit_evidence_rules:
                    implicit_evidence_rules.append(rule)
            for rule in rules.claim_evidence_requirements:
                if rule not in claim_evidence_requirements:
                    claim_evidence_requirements.append(rule)
        return TaxonomyConfig(
            version=self.version,
            structure_version=2 if hierarchical else 1,
            categories=categories,
            agent_family="multi-category",
            product_context="多品类商品",
            allowed_parts=parts,
            instructions=[],
            validation_rules=TaxonomyValidationRules(
                neutral_reason_labels=list(dict.fromkeys(neutral_reason_labels)),
                required_review_labels=list(dict.fromkeys(required_review_labels)),
                allowed_groups=group_sets[0] if all(group_sets) else [],
                conflict_scope="evidence"
                if all(scope == "evidence" for scope in conflict_scopes)
                else "comment",
                opposite_reason_labels=opposite_reason_labels,
                conflicting_label_sets=conflicting_label_sets,
                evidence_requirements=evidence_requirements,
                implicit_evidence_rules=implicit_evidence_rules,
                claim_evidence_requirements=claim_evidence_requirements,
            ),
            labels=list(labels.values()),
        )

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
