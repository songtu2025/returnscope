import json
import urllib.request

from return_semantics.model_client import (
    ModelHTTPError,
    Sub2APIClient,
    Sub2APISettings,
    create_model_client,
    normalize_model_payload,
)
from return_semantics.pipeline import build_cache_key
from return_semantics.schemas import ModelClassification


def _payload(unknown_semantics):
    return {
        "semantic_units": [],
        "unknown_semantics": unknown_semantics,
        "primary_label_codes": [],
        "needs_review": False,
        "review_reasons": [],
    }


def test_normalizes_unknown_semantic_text_field() -> None:
    payload = _payload([{"text": "Don't like", "reason": "没有说明具体对象"}])

    result = ModelClassification.model_validate(normalize_model_payload(payload))

    assert result.unknown_semantics[0].opinion == "Don't like"
    assert result.unknown_semantics[0].evidence == "Don't like"


def test_normalizes_unknown_semantic_string() -> None:
    payload = _payload(["Found same for 1/3 less"])

    result = ModelClassification.model_validate(normalize_model_payload(payload))

    assert result.unknown_semantics[0].evidence == "Found same for 1/3 less"


def test_moves_semantic_unit_out_of_unknown_list() -> None:
    unit = {
        "subject": "PRODUCT",
        "label_code": "OTHER_NOT_AS_EXPECTED",
        "opinion": "不符合预期",
        "sentiment": "NEGATIVE",
        "assertion": "AFFIRMED",
        "part": "UNSPECIFIED",
        "evidence": "not as expected",
        "implicit": False,
        "claim_relation": "NONE",
        "claim_id": None,
    }

    result = ModelClassification.model_validate(
        normalize_model_payload(_payload([unit]))
    )

    assert result.unknown_semantics == []
    assert result.semantic_units[0].label_code == "OTHER_NOT_AS_EXPECTED"


def test_strips_semantic_fields_from_unknown_item() -> None:
    item = {
        "subject": "PRODUCT",
        "opinion": "颜色不喜欢",
        "sentiment": "NEGATIVE",
        "assertion": "AFFIRMED",
        "part": "UNSPECIFIED",
        "evidence": "color is not preferable",
        "implicit": False,
        "claim_relation": "NONE",
        "claim_id": None,
    }

    result = ModelClassification.model_validate(
        normalize_model_payload(_payload([item]))
    )

    assert result.unknown_semantics[0].opinion == "颜色不喜欢"
    assert result.unknown_semantics[0].evidence == "color is not preferable"


def test_normalizes_unknown_semantic_description() -> None:
    item = {
        "description": "处于两个尺码之间",
        "evidence": "just in between sizes",
    }

    result = ModelClassification.model_validate(
        normalize_model_payload(_payload([item]))
    )

    assert result.unknown_semantics[0].opinion == "处于两个尺码之间"
    assert result.unknown_semantics[0].evidence == "just in between sizes"


def test_sub2api_settings_from_env(monkeypatch) -> None:
    monkeypatch.setenv("SUB2API_API_KEY", "sub2-key")
    monkeypatch.setenv("SUB2API_MODEL", "gpt-5.6")
    monkeypatch.setenv("SUB2API_BASE_URL", "https://sub2.example/v1/")
    monkeypatch.setenv("SUB2API_SECONDARY_MODEL", "gpt-5.6-review")
    monkeypatch.setenv("SUB2API_REASONING_EFFORT", "medium")
    monkeypatch.setenv("SUB2API_SECONDARY_REASONING_EFFORT", "high")
    monkeypatch.setenv("SUB2API_USE_FAST", "true")
    monkeypatch.setenv("SUB2API_TIMEOUT", "45")
    monkeypatch.setenv("SUB2API_MAX_WORKERS", "6")

    settings = Sub2APISettings.from_env()
    client = create_model_client()

    assert settings.timeout_seconds == 45
    assert settings.use_fast is True
    assert settings.max_workers == 6
    assert settings.cheap_model == "gpt-5.4-mini"
    assert settings.cheap_reasoning_effort == "medium"
    assert settings.cheap_model_audit_percent == 5
    assert settings.secondary_model == "gpt-5.6-review"
    assert settings.reasoning_effort == "medium"
    assert settings.secondary_reasoning_effort == "high"
    assert isinstance(client, Sub2APIClient)


def test_sub2api_client_uses_responses_payload(monkeypatch) -> None:
    settings = Sub2APISettings(
        api_key="test-key",
        model="gpt-5.6",
        base_url="https://sub2.example/v1",
        retries=0,
        use_fast=True,
    )
    client = Sub2APIClient(settings)
    captured = {}

    def fake_post(payload):
        captured.update(payload)
        content = "```json\n" + json.dumps(_payload([])) + "\n```"
        return {
            "model": "gpt-5.6-20260801",
            "output": [
                {"type": "reasoning", "content": []},
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": content},
                    ],
                },
            ],
            "usage": {
                "input_tokens": 12,
                "output_tokens": 8,
                "input_tokens_details": {
                    "cached_tokens": 5,
                },
            },
        }

    monkeypatch.setattr(client, "_post", fake_post)
    messages = [
        {"role": "system", "content": "只返回 JSON"},
        {"role": "user", "content": "Too small"},
    ]

    result = client.classify(messages)

    assert captured == {
        "model": "gpt-5.6",
        "input": messages,
        "reasoning": {"effort": "medium"},
        "service_tier": "fast",
    }
    assert result.model_name == "gpt-5.6-20260801"
    assert result.usage == {
        "input_tokens": 12,
        "output_tokens": 8,
        "input_tokens_details.cached_tokens": 5,
    }

    client.classify(
        messages,
        model="gpt-5.6-review",
        thinking=True,
    )

    assert captured["model"] == "gpt-5.6-review"
    assert captured["reasoning"] == {"effort": "high"}

    client.classify(
        messages,
        model="gpt-5.4-mini",
    )

    assert captured["reasoning"] == {"effort": "medium"}


def test_sub2api_posts_to_responses_endpoint(monkeypatch) -> None:
    settings = Sub2APISettings(
        api_key="test-key",
        model="gpt-5.6",
        base_url="https://sub2.example/v1/",
        timeout_seconds=37,
    )
    client = Sub2APIClient(settings)
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"output": []}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    client._post({"model": "gpt-5.6", "input": "test"})

    assert captured == {
        "url": "https://sub2.example/v1/responses",
        "authorization": "Bearer test-key",
        "timeout": 37,
    }


def test_sub2api_retries_429_using_retry_after(monkeypatch) -> None:
    settings = Sub2APISettings(
        api_key="test-key",
        model="gpt-5.5",
        base_url="https://sub2.example/v1",
        retries=1,
        requests_per_minute=0,
    )
    client = Sub2APIClient(settings)
    attempts = 0
    sleeps = []

    def fake_post(payload):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ModelHTTPError(
                "Sub2API",
                429,
                "rate limited",
                retry_after=3,
            )
        return {
            "model": payload["model"],
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(_payload([])),
                        }
                    ],
                }
            ],
            "usage": {},
        }

    monkeypatch.setattr(client, "_post", fake_post)
    monkeypatch.setattr(
        "return_semantics.model_client.time.sleep",
        sleeps.append,
    )

    result = client.classify(messages=[])

    assert attempts == 2
    assert sleeps == [3]
    assert result.metrics["attempts"] == 2
    assert result.metrics["retries"] == 1


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
