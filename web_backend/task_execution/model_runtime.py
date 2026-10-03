from __future__ import annotations

from collections.abc import Callable
from dataclasses import is_dataclass, replace
from typing import Any, cast

from return_semantics.capabilities import (
    CategoryCapability,
)
from return_semantics.category_pipeline import CategorySegmentRuntime
from return_semantics.claims import NO_CLAIMS_VERSION, ClaimsResolver
from return_semantics.model_client import (
    RequestRateLimiter,
    Sub2APIClient,
    Sub2APISettings,
)
from web_backend.common import json_value


class ModelRuntimeMixin:
    _capability_for_segment: Callable[..., CategoryCapability]
    _get_rate_limiter: Callable[..., RequestRateLimiter]
    claims_resolver: ClaimsResolver

    def _build_segment_runtime(
        self,
        segment: dict[str, Any],
        base_settings: Any,
        config_version_id: str,
        store: str,
        listing: str | None,
    ) -> CategorySegmentRuntime:
        agent_key = str(segment["agent_key"])
        capability = self._capability_for_segment(segment)

        model_policy = json_value(segment.get("model_policy_json"), None)
        if model_policy is None:
            model_policy = {
                "version": "legacy-model-policy-v1",
                "configured": {
                    "first_pass_role": (
                        "cheap" if base_settings.cheap_model else "primary"
                    ),
                    "review_role": (
                        "secondary" if base_settings.secondary_model else None
                    ),
                },
                "actual": {
                    "primary": {
                        "role": "primary",
                        "model": base_settings.model,
                        "effort": base_settings.reasoning_effort,
                    },
                    "first_pass": {
                        "role": ("cheap" if base_settings.cheap_model else "primary"),
                        "model": base_settings.cheap_model or base_settings.model,
                        "effort": (
                            base_settings.cheap_reasoning_effort
                            if base_settings.cheap_model
                            else base_settings.reasoning_effort
                        ),
                    },
                    "review": (
                        {
                            "role": "secondary",
                            "model": base_settings.secondary_model,
                            "effort": base_settings.secondary_reasoning_effort,
                        }
                        if base_settings.secondary_model
                        else None
                    ),
                },
            }
        elif str(model_policy.get("version")) != capability.model_policy.version:
            raise ValueError(
                f"片段 {segment['segment_key']} 的模型策略版本已不可用，请重新规划"
            )

        actual = model_policy["actual"]
        review = actual.get("review")
        segment_settings = self._settings_for_model_policy(
            base_settings,
            model_policy,
        )
        expected_claims_version = (
            str(segment["claims_version"])
            if segment.get("claims_version")
            else NO_CLAIMS_VERSION
        )
        scope = json_value(segment.get("scope_json"), {})
        claims = self.claims_resolver.resolve(
            str(scope.get("store") or store),
            scope.get("listing") or listing,
            agent_key,
            expected_version=expected_claims_version,
        )
        client = Sub2APIClient(
            segment_settings,
            rate_limiter=self._get_rate_limiter(
                config_version_id,
                segment_settings.requests_per_minute,
            ),
        )
        return CategorySegmentRuntime(
            client=client,
            claims=claims,
            secondary_model=(str(review["model"]) if review else None),
            model_policy=model_policy,
        )

    @staticmethod
    def _settings_for_model_policy(
        base_settings: Any,
        model_policy: dict[str, Any],
    ) -> Any:
        if not is_dataclass(base_settings):
            return base_settings
        settings = cast(Sub2APISettings, base_settings)
        actual = model_policy["actual"]
        primary = actual["primary"]
        first_pass = actual["first_pass"]
        review = actual.get("review")
        return replace(
            settings,
            model=str(primary["model"]),
            reasoning_effort=str(primary["effort"]),
            cheap_model=(
                str(first_pass["model"]) if first_pass["role"] == "cheap" else None
            ),
            cheap_reasoning_effort=str(first_pass["effort"]),
            secondary_model=(str(review["model"]) if review else None),
            secondary_reasoning_effort=(
                str(review["effort"]) if review else str(primary["effort"])
            ),
        )
