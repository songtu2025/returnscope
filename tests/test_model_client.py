import json
import urllib.request

from model_client_helpers import _payload

from return_semantics.model_client import (
    Sub2APIClient,
    Sub2APISettings,
    create_model_client,
)


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
        model_payload = _payload([])
        model_payload["review_diagnostics"] = [
            {
                "code": "MODEL_RESULT_MISMATCH",
                "detail": "模型不得生成系统诊断",
            }
        ]
        content = "```json\n" + json.dumps(model_payload) + "\n```"
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
    assert result.classification.review_diagnostics == []

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
