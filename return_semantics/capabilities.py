from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from return_semantics.schemas import PartCode, TaxonomyConfig
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
    taxonomy_path: Path
    model_policy: ModelPolicy
    variants: tuple[CategoryVariant, ...]


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
                    raise ValueError(f"品类映射重复: {variant.category_a}/{variant.category_b}")
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
        return load_taxonomy(capability.taxonomy_path)

    def combined_taxonomy(self) -> TaxonomyConfig:
        labels = []
        parts: list[PartCode] = []
        label_codes: set[str] = set()
        for capability in self.capabilities:
            taxonomy = self.load_taxonomy(capability)
            for label in taxonomy.labels:
                if label.code in label_codes:
                    raise ValueError(f"跨品类标签编码重复: {label.code}")
                label_codes.add(label.code)
                labels.append(label)
            for part in taxonomy.allowed_parts:
                if part not in parts:
                    parts.append(part)
        return TaxonomyConfig(
            version=self.version,
            agent_family="multi-category",
            product_context="多品类商品",
            allowed_parts=parts,
            instructions=[],
            labels=labels,
        )


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
