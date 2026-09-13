import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from return_semantics.model_client import (
    JsonlCache,
    JsonModelCallResult,
    ModelHTTPError,
)
from return_semantics.pipeline import classify_comments
from return_semantics.schemas import (
    ListingClaimsConfig,
    ProcessingStatus,
    TaxonomyConfig,
)
from web_backend.agent_runner import AgentRunner


class SelectiveFactClient:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(
            model="test-model",
            cheap_model=None,
            max_workers=1,
            cache_namespace="fact-v2-failure-contract",
            reasoning_effort="low",
        )
        self.current_comment = ""

    def generate_json(self, messages, **_kwargs) -> JsonModelCallResult:
        payload = json.loads(messages[1]["content"])
        if "comment" in payload:
            self.current_comment = str(payload["comment"])
        if self.current_comment == "model unavailable":
            http_error = ModelHTTPError("test-provider", 503, "service unavailable")
            raise RuntimeError("模型调用失败") from http_error
        if "existing_facts" in payload:
            response = {"facts": []}
        elif "current_mappings" in payload:
            response = {
                "adjudications": [
                    {
                        "fact_id": "fact-1",
                        "label_code": "WARM",
                        "action": "ACCEPT",
                        "reason": "证据直接支持保暖",
                    }
                ]
            }
        elif "labels" in payload:
            response = {
                "mappings": [
                    {
                        "fact_id": "fact-1",
                        "label_codes": ["WARM"],
                        "reason": "评论明确表示保暖",
                    }
                ]
            }
        else:
            response = {
                "facts": [
                    {
                        "fact_id": "fact-1",
                        "actor_ref": "REVIEWER",
                        "product_ref": "CURRENT",
                        "event_ref": "当前评价",
                        "statement_type": "EVALUATION",
                        "opinion": "商品保暖",
                        "sentiment": "POSITIVE",
                        "part": "UNSPECIFIED",
                        "condition": "",
                        "evidence_spans": [{"text": "warm"}],
                        "candidate_branch_codes": ["功能"],
                    }
                ]
            }
        return JsonModelCallResult(
            response,
            "test-model",
            {"total_tokens": 5},
            {"attempts": 1},
        )


def _taxonomy() -> TaxonomyConfig:
    return TaxonomyConfig.model_validate(
        {
            "version": "fact-v2-failure-contract",
            "recognition_profile": "fact_v2",
            "agent_family": "测试",
            "product_context": "测试商品",
            "labels": [
                {
                    "code": "WARM",
                    "name": "保暖",
                    "group": "功能",
                    "allowed_sentiments": ["POSITIVE"],
                }
            ],
        }
    )


def _comments(*comments: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "classification_key": f"key-{index}",
                "comment_normalized": comment,
                "reason": "OTHER",
            }
            for index, comment in enumerate(comments, start=1)
        ]
    )


def _classify(tmp_path: Path, *comments: str, checkpoint=None):
    return classify_comments(
        unique_comments=_comments(*comments),
        taxonomy=_taxonomy(),
        claims=ListingClaimsConfig(version="none", claims=[]),
        client=SelectiveFactClient(),
        cache=JsonlCache(tmp_path / "cache.jsonl"),
        checkpoint=checkpoint,
    )


def test_fact_v2_model_exception_is_system_failure_not_business_unknown(
    tmp_path: Path,
) -> None:
    run = _classify(tmp_path, "model unavailable")

    result = run.classifications["key-1"]
    assert result.status is ProcessingStatus.MODEL_ERROR
    assert result.unknown_semantics == []
    assert result.problem_label_codes == []
    assert result.positive_label_codes == []
    assert result.review_reasons == ["模型调用失败"]
    assert run.model_failures == 1
    assert run.model_calls == 0


def test_fact_v2_checkpoint_resume_keeps_success_and_excludes_model_error(
    tmp_path: Path,
) -> None:
    checkpoint_snapshots = []
    run = _classify(
        tmp_path,
        "warm",
        "model unavailable",
        checkpoint=checkpoint_snapshots.append,
    )

    successful = run.classifications["key-1"]
    assert successful.status is not ProcessingStatus.MODEL_ERROR
    assert [item.label_code for item in successful.semantic_units] == ["WARM"]
    assert run.classifications["key-2"].status is ProcessingStatus.MODEL_ERROR
    assert AgentRunner._results_have_quality_errors(run.classifications)
    assert [len(item.classifications) for item in checkpoint_snapshots] == [1, 2]

    checkpoint_path = tmp_path / "classifications.json"
    AgentRunner._write_checkpoint(checkpoint_path, run.classifications)
    runner = object.__new__(AgentRunner)
    runner.settings = SimpleNamespace(data_dir=tmp_path)
    context = runner._segment_run_context(
        "task-1",
        "segment-1",
        {},
        {
            "result_json_path": str(checkpoint_path),
            "model_calls": run.model_calls,
            "cache_hits": run.cache_hits,
            "model_failures": run.model_failures,
        },
    )

    assert set(context.existing_results) == {"key-1"}
    assert context.existing_results["key-1"] == successful
    assert context.runtime_totals() == (
        run.model_calls,
        run.cache_hits,
        run.model_failures,
    )
