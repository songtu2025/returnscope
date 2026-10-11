from copy import deepcopy
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from review_router_helpers import (
    BULK_BODY,
    CASES_BY_METHOD,
    RECORD_BODY,
    RECORD_DEFAULTS,
)
from review_router_helpers import harness as harness


@pytest.mark.parametrize(
    "semantic_input,semantic_expected",
    [
        (None, None),
        ([], []),
        (
            [
                {
                    "semantic_item_id": " item-1 ",
                    "action": "no_tag_needed",
                    "label_code": None,
                    "note": None,
                }
            ],
            [{"semantic_item_id": "item-1", "action": "no_tag_needed"}],
        ),
    ],
)
@pytest.mark.parametrize(
    "added_input,added_expected",
    [
        (None, None),
        ([], []),
        (
            [
                {
                    "item_id": None,
                    "evidence_text": " 合成证据 ",
                    "opinion": " 合成观点 ",
                    "label_code": " FIT_TOO_SMALL_U1 ",
                    "note": None,
                }
            ],
            [
                {
                    "evidence_text": "合成证据",
                    "opinion": "合成观点",
                    "label_code": "FIT_TOO_SMALL_U1",
                }
            ],
        ),
    ],
)
def test_single_record_preserves_optional_semantic_details_and_assessment(
    harness: tuple[TestClient, Mock, Mock, Mock],
    semantic_input: Any,
    semantic_expected: Any,
    added_input: Any,
    added_expected: Any,
) -> None:
    client, service, _, _ = harness
    service.update_batch_record.return_value = {"revision": 6}
    assessment = {
        "label_correctness": "partial",
        "evidence_completeness": "missing",
        "review_routing": "correct",
    }
    body = {
        **RECORD_BODY,
        **assessment,
        "action": "modify",
        "label_code": "FIT_TOO_SMALL_U1",
        "semantic_item_reviews": semantic_input,
        "added_semantic_items": added_input,
        "coverage_status": "has_omission",
    }
    before = deepcopy(body)
    response = client.patch(CASES_BY_METHOD["update_batch_record"].path, json=body)
    assert response.status_code == 200
    service.update_batch_record.assert_called_once_with(
        **{
            **RECORD_DEFAULTS,
            "action": "modify",
            "label_code": "FIT_TOO_SMALL_U1",
            "review_assessment": assessment,
            "semantic_item_reviews": semantic_expected,
            "added_semantic_items": added_expected,
            "coverage_status": "has_omission",
        }
    )
    assert body == before


@pytest.mark.parametrize("action", ["confirm", "modify", "exclude"])
def test_bulk_records_preserve_revisions_action_and_assessment(
    harness: tuple[TestClient, Mock, Mock, Mock],
    action: str,
) -> None:
    client, service, _, _ = harness
    service.update_batch_records.return_value = {"revision": 6}
    records = [
        {"id": "review-1", "expected_revision": 5},
        {"id": "review-2", "expected_revision": 8},
    ]
    assessment = {
        "label_correctness": "correct",
        "evidence_completeness": "complete",
        "review_routing": "should_manual_review",
    }
    body = {
        **BULK_BODY,
        **assessment,
        "records": records,
        "action": action,
        "label_code": "FIT_TOO_SMALL_U1",
    }
    response = client.patch(CASES_BY_METHOD["update_batch_records"].path, json=body)
    assert response.status_code == 200
    service.update_batch_records.assert_called_once_with(
        batch_id="batch-1",
        records=records,
        actor_id="42",
        action=action,
        label_code="FIT_TOO_SMALL_U1",
        note="验证批量复核",
        review_assessment=assessment,
    )


@pytest.mark.parametrize("field", ["semantic_item_reviews", "added_semantic_items"])
@pytest.mark.parametrize("sentiment", ["POSITIVE", "NEGATIVE", "NEUTRAL", None])
def test_optional_sentiment_is_forwarded_without_changing_legacy_payload(
    harness: tuple[TestClient, Mock, Mock, Mock],
    field: str,
    sentiment: str | None,
) -> None:
    client, service, _, _ = harness
    service.update_batch_record.return_value = {"revision": 6}
    item = _sentiment_item(field)
    response = client.patch(
        CASES_BY_METHOD["update_batch_record"].path,
        json={**RECORD_BODY, field: [{**item, "sentiment": sentiment}]},
    )
    assert response.status_code == 200
    expected = {**item, **({"sentiment": sentiment} if sentiment is not None else {})}
    assert service.update_batch_record.call_args.kwargs[field] == [expected]


@pytest.mark.parametrize("field", ["semantic_item_reviews", "added_semantic_items"])
@pytest.mark.parametrize("sentiment", ["positive", "", 123])
def test_invalid_sentiment_is_rejected_before_service_or_database(
    harness: tuple[TestClient, Mock, Mock, Mock], field: str, sentiment: Any
) -> None:
    client, service, database, audit = harness
    response = client.patch(
        CASES_BY_METHOD["update_batch_record"].path,
        json={
            **RECORD_BODY,
            field: [{**_sentiment_item(field), "sentiment": sentiment}],
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field, 0, "sentiment"]
    assert service.mock_calls == database.mock_calls == audit.mock_calls == []


def _sentiment_item(field: str) -> dict[str, Any]:
    if field == "semantic_item_reviews":
        return {
            "semantic_item_id": "item-1",
            "action": "change_label",
            "label_code": "FIT_TOO_SMALL_U1",
        }
    return {
        "evidence_text": "合成证据",
        "opinion": "合成观点",
        "label_code": "FIT_TOO_SMALL_U1",
    }
