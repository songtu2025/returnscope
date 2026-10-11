from return_semantics.model_client import (
    Sub2APISettings,
)
from return_semantics.pipeline import build_cache_key


def test_cache_key_isolated_by_reasoning_config() -> None:
    arguments = {
        "comment": "Too small",
        "model_name": "shared-model",
        "taxonomy_version": "v1",
        "claims_version": "v1",
    }
    settings = Sub2APISettings(
        api_key="test-key",
        model="shared-model",
        base_url="https://sub2.example/v1",
    )
    changed_settings = Sub2APISettings(
        api_key="test-key",
        model="shared-model",
        base_url="https://sub2.example/v1",
        secondary_reasoning_effort="xhigh",
    )

    standard_key = build_cache_key(
        provider_name=settings.cache_namespace,
        **arguments,
    )
    changed_effort_key = build_cache_key(
        provider_name=changed_settings.cache_namespace,
        **arguments,
    )

    assert standard_key != changed_effort_key


def test_cache_key_isolated_by_structured_category() -> None:
    arguments = {
        "comment": "Too small",
        "model_name": "shared-model",
        "provider_name": "provider",
        "taxonomy_version": "v1",
        "claims_version": "v1",
    }

    footwear_key = build_cache_key(
        classification_scope="水鞋\x1f薄底水鞋",
        **arguments,
    )
    eyewear_key = build_cache_key(
        classification_scope="眼镜\x1f儿童眼镜",
        **arguments,
    )

    assert footwear_key != eyewear_key


def test_cache_key_isolated_by_claims_policy_and_actual_effort() -> None:
    arguments = {
        "comment": "Too small",
        "model_name": "shared-model",
        "provider_name": "provider",
        "taxonomy_version": "taxonomy-v1",
        "classification_scope": "水鞋\x1f薄底水鞋",
    }
    base = build_cache_key(
        claims_version="claims-v1",
        model_policy_version="policy-v1",
        reasoning_effort="medium",
        **arguments,
    )
    changed_claims = build_cache_key(
        claims_version="claims-v2",
        model_policy_version="policy-v1",
        reasoning_effort="medium",
        **arguments,
    )
    changed_policy = build_cache_key(
        claims_version="claims-v1",
        model_policy_version="policy-v2",
        reasoning_effort="medium",
        **arguments,
    )
    changed_effort = build_cache_key(
        claims_version="claims-v1",
        model_policy_version="policy-v1",
        reasoning_effort="high",
        **arguments,
    )

    assert len({base, changed_claims, changed_policy, changed_effort}) == 4
