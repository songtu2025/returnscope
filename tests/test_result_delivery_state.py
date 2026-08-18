from __future__ import annotations

from pathlib import Path

import pytest
from test_classification_result_pool import _publish, _seed_result_context

from web_backend.classification_result_service import ClassificationResultService
from web_backend.result_state import result_delivery_state


@pytest.mark.parametrize(
    ("quality_status", "delivery_status", "eligible", "blocking_code"),
    [
        ("ready", "ready", True, None),
        ("review_required", "needs_review", True, None),
        ("unusable", "unusable", False, "unusable"),
    ],
)
def test_result_list_detail_and_history_share_delivery_state(
    tmp_path: Path,
    quality_status: str,
    delivery_status: str,
    eligible: bool,
    blocking_code: str | None,
) -> None:
    context = _seed_result_context(tmp_path)
    version = _publish(context)
    version_id = str(version["version_id"])
    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE classification_result_versions
            SET quality_status = ? WHERE id = ?
            """,
            (quality_status, version_id),
        )

    service = ClassificationResultService(context.database)
    responses = [
        service.get(version_id),
        service.list()["items"][0],
        service.history(version_id)[0],
    ]
    for item in responses:
        assert item["quality_status"] == quality_status
        assert item["publish_status"] == "published"
        assert item["delivery_status"] == delivery_status
        assert item["publish_origin"] == "original-classification"
        assert item["dashboard_eligibility"] is eligible
        assert [reason["code"] for reason in item["blocking_reasons"]] == (
            [] if blocking_code is None else [blocking_code]
        )


def test_review_derived_version_is_dashboard_eligible(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    base = _publish(context)
    base_id = str(base["version_id"])
    derived_id = "classification-version-derived"
    with context.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO classification_result_versions(
                id, result_id, source_segment_id, version_no, content_hash,
                quality_status, publish_status, unit_count, record_count,
                parent_version_id, version_reason, created_by, created_at,
                published_at
            )
            SELECT ?, result_id, source_segment_id, 2, 'derived-content-hash',
                   'ready', 'published', unit_count, record_count, id,
                   '人工复核发布', created_by, created_at, published_at
            FROM classification_result_versions WHERE id = ?
            """,
            (derived_id, base_id),
        )

    service = ClassificationResultService(context.database)
    detail = service.get(derived_id)
    assert detail["quality_status"] == "ready"
    assert detail["delivery_status"] == "review-derived"
    assert detail["publish_origin"] == "review-derived"
    assert detail["dashboard_eligibility"] is True
    assert detail["blocking_reasons"] == []
    assert service.list()["items"][0]["version_id"] == derived_id
    assert service.history(derived_id)[0]["delivery_status"] == "review-derived"


def test_unpublished_result_reports_publish_blocker() -> None:
    state = result_delivery_state(
        quality_status="ready",
        publish_status="publishing",
    )
    assert state["delivery_status"] == "ready"
    assert state["dashboard_eligibility"] is False
    assert state["blocking_reasons"] == [
        {
            "code": "not_published",
            "message": "分类结果版本尚未发布",
        }
    ]
