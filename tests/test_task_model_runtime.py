import json
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from return_semantics.claims import NO_CLAIMS_VERSION
from return_semantics.model_client import Sub2APISettings
from web_backend.task_execution.model_runtime import ModelRuntimeMixin


def _runtime(monkeypatch, cheap, secondary, plain):
    settings = Sub2APISettings(
        api_key="test-key",
        model="primary",
        base_url="https://example.test",
        cheap_model=cheap,
        secondary_model=secondary,
        reasoning_effort="medium",
        cheap_reasoning_effort="low",
        secondary_reasoning_effort="high",
    )
    before = asdict(settings)
    if plain:
        settings = SimpleNamespace(**before)
    runtime = ModelRuntimeMixin()
    runtime._capability_for_segment = Mock(
        return_value=SimpleNamespace(model_policy=SimpleNamespace(version="policy-v1"))
    )
    runtime.claims_resolver = Mock()
    runtime._get_rate_limiter = Mock(return_value=object())
    client = Mock()
    monkeypatch.setattr(
        "web_backend.task_execution.model_runtime.Sub2APIClient", client
    )
    return runtime, settings, before, client


def _policy():
    return {
        "version": "policy-v1",
        "configured": {"first_pass_role": "cheap", "review_role": "secondary"},
        "actual": {
            "primary": {"role": "primary", "model": "frozen-primary", "effort": "high"},
            "first_pass": {
                "role": "cheap",
                "model": "frozen-cheap",
                "effort": "medium",
            },
            "review": {"role": "secondary", "model": "frozen-review", "effort": "low"},
        },
    }


@pytest.mark.parametrize("cheap", [None, "cheap"])
@pytest.mark.parametrize("secondary", [None, "secondary"])
@pytest.mark.parametrize("plain", [False, True])
def test_legacy_roles_preserve_settings_claims_and_rate_limiter(
    monkeypatch, cheap, secondary, plain
):
    runtime, settings, before, client = _runtime(monkeypatch, cheap, secondary, plain)
    segment = {
        "agent_key": "footwear",
        "segment_key": "synthetic",
        "model_policy_json": None,
    }
    result = runtime._build_segment_runtime(
        segment, settings, "config-1", "shop", "listing"
    )
    policy = result.model_policy
    assert policy["version"] == "legacy-model-policy-v1"
    assert policy["actual"]["first_pass"]["model"] == (cheap or "primary")
    assert policy["actual"]["first_pass"]["effort"] == ("low" if cheap else "medium")
    assert result.secondary_model == secondary
    runtime.claims_resolver.resolve.assert_called_once_with(
        "shop", "listing", "footwear", expected_version=NO_CLAIMS_VERSION
    )
    runtime._get_rate_limiter.assert_called_once_with(
        "config-1", settings.requests_per_minute
    )
    client.assert_called_once()
    assert client.call_args.kwargs == {
        "rate_limiter": runtime._get_rate_limiter.return_value
    }
    assert (vars(settings) if plain else asdict(settings)) == before
    assert (client.call_args.args[0] is settings) == plain


@pytest.mark.parametrize("plain", [False, True])
@pytest.mark.parametrize(
    "scope",
    [
        {},
        {"store": "", "listing": ""},
        {"store": "saved-shop", "listing": "saved-listing"},
    ],
)
def test_persisted_policy_and_claim_scope_take_priority(monkeypatch, plain, scope):
    runtime, settings, before, client = _runtime(monkeypatch, None, None, plain)
    policy = _policy()
    segment = {
        "agent_key": "footwear",
        "segment_key": "synthetic",
        "model_policy_json": json.dumps(policy),
        "claims_version": "claims-v1",
        "scope_json": json.dumps(scope),
    }
    result = runtime._build_segment_runtime(
        segment, settings, "config-1", "shop", "listing"
    )
    assert result.model_policy == policy and result.secondary_model == "frozen-review"
    runtime.claims_resolver.resolve.assert_called_once_with(
        scope.get("store") or "shop",
        scope.get("listing") or "listing",
        "footwear",
        expected_version="claims-v1",
    )
    actual = client.call_args.args[0]
    if plain:
        assert actual is settings
    else:
        assert (actual.model, actual.cheap_model, actual.secondary_model) == (
            "frozen-primary",
            "frozen-cheap",
            "frozen-review",
        )
        assert (
            actual.reasoning_effort,
            actual.cheap_reasoning_effort,
            actual.secondary_reasoning_effort,
        ) == ("high", "medium", "low")
    assert (vars(settings) if plain else asdict(settings)) == before


def test_policy_version_error_precedes_claims_and_client(monkeypatch):
    runtime, settings, _before, client = _runtime(monkeypatch, None, None, False)
    runtime.claims_resolver.resolve.side_effect = RuntimeError("不应调用声明")
    policy = _policy()
    policy["version"] = "obsolete"
    segment = {
        "agent_key": "footwear",
        "segment_key": "synthetic",
        "model_policy_json": json.dumps(policy),
    }
    with pytest.raises(ValueError, match="模型策略版本已不可用"):
        runtime._build_segment_runtime(segment, settings, "config-1", "shop", "listing")
    runtime.claims_resolver.resolve.assert_not_called()
    runtime._get_rate_limiter.assert_not_called()
    client.assert_not_called()
