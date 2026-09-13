from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pandas as pd

from return_semantics.model_client import JsonlCache, ModelCallResult
from return_semantics.pipeline import PipelineRun, classify_comments
from return_semantics.schemas import ModelClassification

_WAIT_TIMEOUT_SECONDS = 5


def _classification(evidence: str) -> ModelClassification:
    return ModelClassification.model_validate(
        {
            "semantic_units": [
                {
                    "subject": "PRODUCT",
                    "label_code": "FIT_TOO_SMALL",
                    "opinion": "尺码偏小",
                    "sentiment": "NEGATIVE",
                    "assertion": "AFFIRMED",
                    "part": "WHOLE_SHOE",
                    "evidence": evidence,
                    "implicit": False,
                    "claim_relation": "NONE",
                    "claim_id": None,
                }
            ],
            "unknown_semantics": [],
            "primary_label_codes": ["FIT_TOO_SMALL"],
            "needs_review": False,
            "review_reasons": [],
        }
    )


class ControlledClient:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(
            model="test-model",
            cheap_model=None,
            max_workers=2,
            cache_namespace="timeout-isolation",
        )
        self.slow_started = Event()
        self.fast_finished = Event()
        self.release_slow = Event()

    def classify(self, messages, model=None, thinking=False) -> ModelCallResult:
        prompt = "\n".join(message["content"] for message in messages)
        if "slow request" in prompt:
            self.slow_started.set()
            if not self.release_slow.wait(timeout=_WAIT_TIMEOUT_SECONDS):
                raise AssertionError("测试未释放受控慢请求")
            evidence = "slow request"
        else:
            if not self.slow_started.wait(timeout=_WAIT_TIMEOUT_SECONDS):
                raise AssertionError("受控慢请求未先启动")
            evidence = "fast request"
            self.fast_finished.set()
        return ModelCallResult(
            classification=_classification(evidence),
            model_name=model or self.settings.model,
            usage={"total_tokens": 1},
            metrics={"attempts": 1},
        )


def test_fast_result_is_checkpointed_before_first_slow_result(
    tmp_path,
    taxonomy,
    claims,
) -> None:
    client = ControlledClient()
    comments = pd.DataFrame(
        [
            {
                "classification_key": "key-slow",
                "comment_normalized": "slow request",
                "reason": "APPAREL_TOO_SMALL",
            },
            {
                "classification_key": "key-fast",
                "comment_normalized": "fast request",
                "reason": "APPAREL_TOO_SMALL",
            },
        ]
    )
    checkpoint_snapshots: list[list[str]] = []
    fast_checkpointed = Event()

    def checkpoint(run: PipelineRun) -> None:
        keys = list(run.classifications)
        checkpoint_snapshots.append(keys)
        if keys == ["key-fast"] and not client.release_slow.is_set():
            fast_checkpointed.set()

    with ThreadPoolExecutor(max_workers=1) as caller:
        future = caller.submit(
            classify_comments,
            unique_comments=comments,
            taxonomy=taxonomy,
            claims=claims,
            client=client,
            cache=JsonlCache(tmp_path / "cache.jsonl"),
            checkpoint=checkpoint,
        )
        try:
            assert client.slow_started.wait(timeout=_WAIT_TIMEOUT_SECONDS)
            assert client.fast_finished.wait(timeout=_WAIT_TIMEOUT_SECONDS)
            assert fast_checkpointed.wait(timeout=_WAIT_TIMEOUT_SECONDS)
        finally:
            client.release_slow.set()
        run = future.result(timeout=_WAIT_TIMEOUT_SECONDS)

    assert checkpoint_snapshots == [
        ["key-fast"],
        ["key-fast", "key-slow"],
    ]
    assert list(run.classifications) == ["key-slow", "key-fast"]
