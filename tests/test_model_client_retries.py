import json

import pytest
from model_client_helpers import _payload

from return_semantics.model_client import (
    ModelHTTPError,
    Sub2APIClient,
    Sub2APISettings,
)


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


def test_sub2api_retries_read_timeout(monkeypatch) -> None:
    settings = Sub2APISettings(
        api_key="test-key",
        model="gpt-5.5",
        base_url="https://sub2.example/v1",
        retries=1,
        requests_per_minute=0,
        retry_base_seconds=0,
    )
    client = Sub2APIClient(settings)
    attempts = 0

    def fake_post(payload):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("The read operation timed out")
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
        lambda _seconds: None,
    )

    result = client.classify(messages=[])

    assert attempts == 2
    assert result.metrics["attempts"] == 2
    assert result.metrics["retries"] == 1


def test_sub2api_stops_after_second_read_timeout(monkeypatch) -> None:
    settings = Sub2APISettings(
        api_key="test-key",
        model="gpt-5.5",
        base_url="https://sub2.example/v1",
        retries=5,
        requests_per_minute=0,
        retry_base_seconds=0,
    )
    client = Sub2APIClient(settings)
    attempts = 0

    def fake_post(_payload):
        nonlocal attempts
        attempts += 1
        raise TimeoutError("The read operation timed out")

    monkeypatch.setattr(client, "_post", fake_post)
    monkeypatch.setattr(
        "return_semantics.model_client.time.sleep",
        lambda _seconds: None,
    )

    with pytest.raises(RuntimeError, match="Sub2API 调用失败"):
        client.classify(messages=[])

    assert attempts == 2
