from __future__ import annotations

from dataclasses import is_dataclass, replace
from typing import Any

from return_semantics.capabilities import CategoryCapability
from return_semantics.schemas import TaxonomyConfig
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.config_service import ConfigService


class SegmentConfigurationMixin:
    capability_registry: Any
    config_service: ConfigService
    standard_service: ClassificationStandardService

    def _snapshot_model_settings(
        self,
        task: dict[str, Any],
        snapshot: dict[str, Any],
    ) -> Any:
        model_settings = self.config_service.build_model_settings(
            str(task["config_version_id"])
        )
        snapshot_config = snapshot.get("config", {})
        if snapshot_config.get("primary_model") and is_dataclass(model_settings):
            return replace(
                model_settings,
                model=str(snapshot_config["primary_model"]),
                reasoning_effort=str(
                    snapshot_config.get(
                        "primary_effort",
                        model_settings.reasoning_effort,
                    )
                ),
                cheap_model=snapshot_config.get("cheap_model"),
                cheap_reasoning_effort=str(
                    snapshot_config.get(
                        "cheap_effort",
                        model_settings.cheap_reasoning_effort,
                    )
                ),
                cheap_model_audit_percent=int(
                    snapshot_config.get(
                        "cheap_audit_percent",
                        model_settings.cheap_model_audit_percent,
                    )
                ),
                secondary_model=snapshot_config.get("secondary_model"),
                secondary_reasoning_effort=str(
                    snapshot_config.get(
                        "secondary_effort",
                        model_settings.secondary_reasoning_effort,
                    )
                ),
            )
        return model_settings

    def _capability_for_segment(
        self,
        segment: dict[str, Any],
    ) -> CategoryCapability:
        standard_version_id = str(segment.get("standard_version_id") or "")
        if standard_version_id:
            return self.standard_service.capability_for_version(standard_version_id)
        agent_key = str(segment["agent_key"])
        capability = next(
            (
                item
                for item in self.capability_registry.capabilities
                if item.key == agent_key
            ),
            None,
        )
        if capability is None:
            raise ValueError(f"品类能力不存在: {agent_key}")
        return capability

    def _taxonomy_for_segment(
        self,
        segment: dict[str, Any],
        capability: CategoryCapability,
    ) -> TaxonomyConfig:
        standard_version_id = str(segment.get("standard_version_id") or "")
        if standard_version_id:
            return self.standard_service.taxonomy_for_version(standard_version_id)
        return self.capability_registry.load_taxonomy(capability)
