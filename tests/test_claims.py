from __future__ import annotations

import json
from pathlib import Path

from return_semantics.claims import NO_CLAIMS_VERSION, ClaimsResolver
from return_semantics.model_client import Sub2APISettings
from web_backend.agent_runner import AgentRunner
from web_backend.database import Database
from web_backend.settings import PROJECT_ROOT, Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "runtime",
        database_path=tmp_path / "app.db",
        session_days=14,
        task_workers=1,
        bootstrap_email="admin@example.com",
        bootstrap_name="管理员",
        bootstrap_password="test-password",
        encryption_key="test-key",
        secure_cookies=False,
    )


def test_sk001_claims_load_and_unconfigured_listing_has_no_claims() -> None:
    resolver = ClaimsResolver(
        PROJECT_ROOT / "config" / "listing_claims_registry.json"
    )

    configured = resolver.resolve("SEEKWAY:US", "SK001", "footwear")
    unconfigured = resolver.resolve("SEEKWAY:US", "OTHER", "footwear")

    assert configured.version == "sk001-listing-2026-08-05-v1"
    assert configured.claims
    assert unconfigured.version == NO_CLAIMS_VERSION
    assert unconfigured.claims == []


def test_runner_uses_persisted_claims_and_legacy_snapshot_is_safe(tmp_path: Path) -> None:
    runner = AgentRunner(Database(tmp_path / "app.db"), _settings(tmp_path), object())
    base_settings = Sub2APISettings(
        api_key="test-key",
        model="primary-model",
        base_url="https://example.test",
        cheap_model=None,
        secondary_model=None,
    )
    capability = next(
        item
        for item in runner.capability_registry.capabilities
        if item.key == "footwear"
    )
    policy = {
        "version": capability.model_policy.version,
        "configured": {"first_pass_role": "primary", "review_role": None},
        "actual": {
            "primary": {
                "role": "primary",
                "model": "primary-model",
                "effort": "medium",
            },
            "first_pass": {
                "role": "primary",
                "model": "primary-model",
                "effort": "medium",
            },
            "review": None,
        },
    }
    segment = {
        "segment_key": "footwear",
        "agent_key": "footwear",
        "model_policy_json": json.dumps(policy),
        "claims_version": "sk001-listing-2026-08-05-v1",
    }

    runtime = runner._build_segment_runtime(
        segment,
        base_settings,
        "config-v1",
        "SEEKWAY:US",
        "SK001",
    )
    legacy_runtime = runner._build_segment_runtime(
        {
            "segment_key": "footwear",
            "agent_key": "footwear",
            "model_policy_json": None,
            "claims_version": None,
        },
        base_settings,
        "config-v1",
        "SEEKWAY:US",
        "SK001",
    )

    assert runtime.claims.version == "sk001-listing-2026-08-05-v1"
    assert runtime.claims.claims
    assert legacy_runtime.model_policy["version"] == "legacy-model-policy-v1"
    assert legacy_runtime.claims.version == NO_CLAIMS_VERSION
