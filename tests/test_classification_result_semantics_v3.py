from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_classification_result_pool import _publish, _seed_result_context

from return_semantics.schemas import ProcessingStatus
from web_backend.classification_result_service import ClassificationResultService
from web_backend.common import json_text
from web_backend.routers.classification_results import (
    create_classification_result_router,
)


class ResultPayload:
    def __init__(
        self,
        source: Any,
        payload: dict[str, Any],
        status: ProcessingStatus,
    ) -> None:
        self.status = status
        self.problem_label_codes = payload.get("problem_label_codes", [])
        self.positive_label_codes = payload.get("positive_label_codes", [])
        self.primary_label_codes = payload.get("primary_label_codes", [])
        self.model_name = source.model_name
        self.prompt_version = source.prompt_version
        self.taxonomy_version = source.taxonomy_version
        self._payload = payload

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return self._payload


def _client(service: ClassificationResultService) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_classification_result_router(
            service,
            lambda: {"id": "user-1"},
        )
    )
    return TestClient(app)


def test_v3_facts_and_comment_topic_summary_are_persisted_and_returned(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    source = context.results[context.key]
    payload = source.model_dump(mode="json")
    payload["extracted_facts"] = [
        {
            "fact_id": "F1",
            "actor_ref": "REVIEWER",
            "product_ref": "CURRENT",
            "event_ref": "E1",
            "subject": "PRODUCT",
            "statement_type": "EXPERIENCE",
            "opinion": "尺码偏小",
            "sentiment": "NEGATIVE",
            "part": "WHOLE_SHOE",
            "operation": "试穿",
            "condition": "本人试穿",
            "is_primary_reason": True,
            "candidate_branch_codes": [],
            "evidence_spans": [{"text": "Too small"}],
        },
        {
            "fact_id": "F2",
            "actor_ref": "OTHER_USER",
            "product_ref": "CURRENT",
            "event_ref": "E2",
            "subject": "PRODUCT",
            "statement_type": "EXPERIENCE",
            "opinion": "家人穿着合脚",
            "sentiment": "POSITIVE",
            "part": "WHOLE_SHOE",
            "operation": "试穿",
            "condition": "家人试穿",
            "is_primary_reason": False,
            "candidate_branch_codes": [],
            "evidence_spans": [{"text": "Fits my wife"}],
        },
    ]
    payload["fact_mappings"] = [
        {
            "fact_id": "F1",
            "label_codes": ["FUNCTION_PROTECTION_U1"],
            "reason": "",
        },
        {
            "fact_id": "F2",
            "label_codes": ["FUNCTION_PROTECTION_U1"],
            "reason": "",
        },
    ]
    payload["semantic_units"] = [
        {
            **payload["semantic_units"][0],
            "label_code": "FUNCTION_PROTECTION_U1",
            "fact_id": "F1",
            "actor_ref": "REVIEWER",
            "product_ref": "CURRENT",
            "event_ref": "E1",
            "statement_type": "EXPERIENCE",
            "operation": "试穿",
            "condition": "本人试穿",
            "evidence_source": "BODY",
        },
        {
            **payload["semantic_units"][0],
            "label_code": "FUNCTION_PROTECTION_U1",
            "opinion": "家人穿着合脚",
            "sentiment": "POSITIVE",
            "evidence": "Fits my wife",
            "fact_id": "F2",
            "actor_ref": "OTHER_USER",
            "product_ref": "CURRENT",
            "event_ref": "E2",
            "statement_type": "EXPERIENCE",
            "operation": "试穿",
            "condition": "家人试穿",
            "evidence_source": "BODY",
        },
    ]
    payload["problem_label_codes"] = ["FUNCTION_PROTECTION_U1"]
    payload["positive_label_codes"] = ["FUNCTION_PROTECTION_U1"]
    payload["primary_label_codes"] = ["FUNCTION_PROTECTION_U1"]
    context.results = {
        context.key: ResultPayload(source, payload, ProcessingStatus.AUTO_APPROVED)
    }

    version = _publish(context)
    version_id = str(version["version_id"])
    service = ClassificationResultService(context.database)
    service.taxonomy = lambda _version_id: context.taxonomy
    response = _client(service).get(f"/api/classification-results/{version_id}/records")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["processing_status"] == "AUTO_APPROVED"
    assert item["semantic_disposition"] == "MAPPED"
    assert item["quality_status"] == "ready"
    assert item["fact_count"] == 2
    assert item["event_count"] == 2
    assert item["atomic_facts"][0] == item["classification"]["semantic_units"][0]
    assert item["atomic_facts"][0]["fact_id"] == "F1"
    assert item["atomic_facts"][0]["actor_ref"] == "REVIEWER"
    assert item["atomic_facts"][0]["operation"] == "试穿"
    assert item["atomic_facts"][0]["condition"] == "本人试穿"
    assert item["atomic_facts"][0]["evidence_source"] == "BODY"
    assert item["atomic_facts"][0]["fact_text_zh"] == "尺码偏小"
    assert item["atomic_facts"][0]["original_evidence"] == "Too small"
    assert item["atomic_facts"][0]["object_ref"] == "CURRENT"
    assert item["atomic_facts"][0]["usage_task"] == "试穿"
    assert item["atomic_facts"][0]["scenario"] == "本人试穿"
    assert item["atomic_facts"][0]["certainty"] == "AFFIRMED"
    assert item["atomic_facts"][0]["causal_attribution"] == "UNKNOWN"
    assert item["atomic_facts"][0]["label_path"]
    assert item["atomic_facts"][0]["label_code_path"]
    assert item["comment_summary_status"] == "MIXED"
    semantic_review = item["classification"]["semantic_review"]
    assert len(semantic_review["semantic_items"]) == 2
    assert semantic_review["coverage_summary"]["mapped"] == 2
    assert semantic_review["unexplained_fragments"] == []
    topic = item["comment_conclusions"][0]
    assert topic["status"] == "MIXED"
    assert topic["supporting_fact_ids"] == ["F1", "F2"]

    with context.database.connect() as connection:
        stored = connection.execute(
            "SELECT classification_json FROM classification_units"
        ).fetchone()[0]
    stored_payload = json.loads(stored)
    assert stored_payload["semantic_units"][0]["fact_id"] == "F1"
    assert stored_payload["comment_summary"]["status"] == "MIXED"
    assert "atomic_facts" not in stored_payload
    assert "comment_conclusions" not in stored_payload
    assert "semantic_review" not in stored_payload

    summary = _client(service).get(f"/api/classification-results/{version_id}/summary")
    assert summary.status_code == 200
    assert summary.json()["metrics"] == {
        "primary_unit": "comment",
        "comment_count": 3,
        "source_record_count": 3,
        "fact_count": 6,
        "event_count": 6,
    }
    assert summary.json()["topic_summaries"][0]["comment_count"] == 3
    assert summary.json()["comment_statuses"] == [
        {"status": "MIXED", "comment_count": 3}
    ]


def test_expected_abstention_does_not_require_review(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    source = context.results[context.key]
    payload = source.model_dump(mode="json")
    payload["semantic_units"] = []
    payload["problem_label_codes"] = []
    payload["positive_label_codes"] = []
    payload["primary_label_codes"] = []
    payload["unknown_semantics"] = [
        {
            "opinion": "未来可能保暖",
            "evidence": "They should be warm",
            "reason": "未来预测不形成确定性能标签",
            "disposition": "EXPECTED_ABSTENTION",
        }
    ]
    context.results = {
        context.key: ResultPayload(source, payload, ProcessingStatus.UNKNOWN_SEMANTIC)
    }

    version = _publish(context)
    service = ClassificationResultService(context.database)
    records = service.records(str(version["version_id"]))

    assert version["quality_status"] == "ready"
    assert records["items"][0]["quality_status"] == "ready"
    assert records["items"][0]["processing_status"] == "UNKNOWN_SEMANTIC"
    assert records["items"][0]["semantic_disposition"] == "EXPECTED_ABSTENTION"
    assert records["items"][0]["unknown_semantics"] == []
    assert len(records["items"][0]["ignored_semantics"]) == 1
    assert (
        records["items"][0]["ignored_semantics"][0]["disposition"]
        == "EXPECTED_ABSTENTION"
    )
    assert records["items"][0]["comment_conclusions"] == []
    assert records["items"][0]["comment_summary_status"] == "NO_CONFIRMED"


def test_evidence_only_does_not_require_review(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    source = context.results[context.key]
    payload = source.model_dump(mode="json")
    payload["semantic_units"] = []
    payload["problem_label_codes"] = []
    payload["positive_label_codes"] = []
    payload["primary_label_codes"] = []
    payload["unknown_semantics"] = [
        {
            "opinion": "用于解释结论的辅助事实",
            "evidence": "The liner explains the warmth",
            "reason": "该事实只支撑其他已确认结论",
            "disposition": "EVIDENCE_ONLY",
        }
    ]
    context.results = {
        context.key: ResultPayload(source, payload, ProcessingStatus.UNKNOWN_SEMANTIC)
    }

    version = _publish(context)
    records = ClassificationResultService(context.database).records(
        str(version["version_id"])
    )

    item = records["items"][0]
    assert version["quality_status"] == "ready"
    assert item["quality_status"] == "ready"
    assert item["semantic_disposition"] == "EVIDENCE_ONLY"
    assert item["unknown_semantics"] == []
    assert item["ignored_semantics"][0]["disposition"] == "EVIDENCE_ONLY"


def test_legacy_classification_json_gets_safe_v3_defaults(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    version = _publish(context)
    legacy = context.results[context.key].model_dump(mode="json")
    for unit in legacy["semantic_units"]:
        for field in (
            "fact_id",
            "actor_ref",
            "product_ref",
            "event_ref",
            "statement_type",
            "condition",
            "evidence_source",
        ):
            unit.pop(field, None)
    legacy["extracted_facts"] = []
    legacy["fact_mappings"] = []
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_units SET classification_json = ?",
            (json_text(legacy),),
        )

    item = ClassificationResultService(context.database).records(
        str(version["version_id"])
    )["items"][0]

    assert item["semantic_disposition"] == "MAPPED"
    assert item["atomic_facts"][0]["fact_id"] is None
    assert item["atomic_facts"][0]["evidence_source"] == "UNKNOWN"
    assert item["atomic_facts"][0]["label_path"] == []
    assert item["atomic_facts"][0]["label_code_path"] == []
    assert item["comment_conclusions"][0]["status"] == "NEGATIVE"
    assert item["comment_summary_status"] == "NEGATIVE"
