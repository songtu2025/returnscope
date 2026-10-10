from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_result_version_reviews import _publish_review_required

from web_backend.classification_result_publication import (
    ResultPublicationConflict,
    SegmentPublicationState,
)
from web_backend.classification_result_queries import system_rerun_count
from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_results.effective_content import load_content
from web_backend.classification_results.manual_correction import correct_group
from web_backend.dashboard_service import DashboardService
from web_backend.dashboards.live_sources import refresh_related_dashboards
from web_backend.routers.classification_results import (
    create_classification_result_router,
)
from web_backend.task_execution.effective_results import current_inherited_results


def _items():
    return [
        {
            "evidence_text": "Too small",
            "opinion": "整体尺寸偏小",
            "label_code": "FIT_TOO_SMALL_U1",
            "sentiment": "NEGATIVE",
        }
    ]


def _record(context, version):
    with context.database.connect() as connection:
        return connection.execute(
            "SELECT id FROM classification_result_records WHERE result_version_id = ? AND order_id = 'ORDER-DUP'",
            (version["version_id"],),
        ).fetchone()[0]


def test_manual_correction_splits_only_current_feedback_group(tmp_path: Path):
    context, version = _publish_review_required(tmp_path)
    service = ClassificationResultService(context.database)
    corrected = correct_group(
        service, version["version_id"], _record(context, version), _items(), "user-2"
    )
    with context.database.connect() as connection:
        content = load_content(connection, corrected["version_id"])
        rows = content["records"]
        target = [row for row in rows if row["order_id"] == "ORDER-DUP"]
        other = [row for row in rows if row["order_id"] == "ORDER-OTHER"]
        assert len(target) == 2
        assert len(other) == 1
        assert target[0]["classification_key"] == target[1]["classification_key"]
        assert target[0]["classification_key"] != other[0]["classification_key"]
        assert all(row["quality_status"] == "ready" for row in target)
        assert other[0]["quality_status"] == "review_required"
        assert system_rerun_count(connection, corrected["version_id"]) == 0
    unchanged = correct_group(
        service,
        corrected["version_id"],
        _record(context, corrected),
        _items(),
        "user-2",
    )
    assert unchanged["version_id"] == corrected["version_id"]
    with pytest.raises(ResultPublicationConflict):
        correct_group(
            service,
            version["version_id"],
            _record(context, version),
            _items(),
            "user-2",
        )


def test_manual_correction_rejects_running_and_invalid_evidence(tmp_path: Path):
    context, version = _publish_review_required(tmp_path)
    service = ClassificationResultService(context.database)
    record_id = _record(context, version)
    with pytest.raises(ValueError):
        correct_group(
            service,
            version["version_id"],
            record_id,
            [{**_items()[0], "evidence_text": "不存在的原文"}],
            "user-2",
        )
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET status = 'running' WHERE id = ?",
            (context.segment_id,),
        )
    with pytest.raises(ResultPublicationConflict):
        correct_group(service, version["version_id"], record_id, _items(), "user-2")


def test_manual_correction_can_remove_all_semantics(tmp_path: Path):
    context, version = _publish_review_required(tmp_path)
    service = ClassificationResultService(context.database)
    corrected = correct_group(
        service, version["version_id"], _record(context, version), [], "user-2"
    )
    group = service.record_groups(corrected["version_id"], order_id="ORDER-DUP")[
        "items"
    ][0]
    assert group["record"]["classification"]["semantic_units"] == []
    assert group["record"]["quality_status"] == "ready"
    assert not group["record"]["system_rerun_required"]


def test_manual_correction_api_enforces_authentication_and_validation(tmp_path: Path):
    context, version = _publish_review_required(tmp_path)
    app = FastAPI()

    def current_user():
        raise HTTPException(status_code=401, detail="请登录")

    app.include_router(
        create_classification_result_router(
            ClassificationResultService(context.database), current_user
        )
    )
    client = TestClient(app)
    url = f"/api/classification-results/{version['version_id']}/records/{_record(context, version)}/semantics"
    assert client.patch(url, json={"semantic_items": _items()}).status_code == 401
    app.dependency_overrides[current_user] = lambda: {"id": "user-2"}
    assert (
        client.patch(
            url, json={"semantic_items": [{**_items()[0], "label_code": "INVALID"}]}
        ).status_code
        == 400
    )
    assert (
        client.patch(
            url, json={"semantic_items": [{**_items()[0], "sentiment": "POSITIVE"}]}
        ).status_code
        == 400
    )
    response = client.patch(url, json={"semantic_items": _items()})
    assert response.status_code == 200
    assert response.json()["version_id"] != version["version_id"]
    assert client.patch(url, json={"semantic_items": _items()}).status_code == 409


def test_manual_correction_updates_existing_dashboard_and_preserves_scope(
    tmp_path: Path,
):
    context, version = _publish_review_required(tmp_path)
    dashboards = DashboardService(context.database)
    filters = {
        "quality_status": ["ready", "review_required"],
        "order_id": ["ORDER-DUP"],
    }
    ids = [version["version_id"]]
    plan = dashboards.preflight(ids, filters)
    board = dashboards.create(
        name="测试看板",
        description="",
        result_version_ids=ids,
        filters=filters,
        plan_hash=plan["plan_hash"],
        reason="测试",
        actor_id="user-1",
    )
    corrected = correct_group(
        ClassificationResultService(context.database),
        version["version_id"],
        _record(context, version),
        _items(),
        "user-2",
    )
    current = dashboards.get(board["id"])
    assert current["version"]["version_id"] != board["version"]["version_id"]
    assert (
        current["version"]["source_snapshot"][0]["result_version_id"]
        == corrected["version_id"]
    )
    assert current["version"]["filters"] == filters
    assert current["version"]["summary"]["record_count"] == 1
    assert current["version"]["summary"]["pending_review_comment_count"] == 0
    assert (
        dashboards.get(board["id"], board["version"]["version_id"])["version"]
        == board["version"]
    )
    # 模拟部署前已存在、仍绑定旧结果的看板，启动时同样追平最新结果。
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE analysis_dashboards SET current_version_id = ? WHERE id = ?",
            (board["version"]["version_id"], board["id"]),
        )
        refresh_related_dashboards(
            context.database, connection, None, "2026-10-10T00:00:00Z"
        )
    restored = dashboards.get(board["id"])
    assert (
        restored["version"]["source_snapshot"] == current["version"]["source_snapshot"]
    )
    with context.database.transaction() as connection:
        refresh_related_dashboards(
            context.database, connection, None, "2026-10-10T00:00:00Z"
        )
    assert dashboards.get(board["id"])["version"] == restored["version"]


def test_partial_rerun_preserves_manual_group_and_unchanged_retry_does_not_publish(
    tmp_path: Path,
):
    context, version = _publish_review_required(tmp_path)
    service = ClassificationResultService(context.database)
    # 让尚未人工修正的订单处于真实可重跑状态。
    from return_semantics.schemas import ProcessingStatus, ReviewDiagnostic

    source = context.results[context.key].model_copy(
        update={
            "status": ProcessingStatus.MANUAL_REVIEW,
            "review_diagnostics": [
                ReviewDiagnostic(
                    code="SECONDARY_MODEL_TIMEOUT",
                    detail="测试超时",
                    action="SYSTEM_RERUN",
                )
            ],
        }
    )
    with context.database.transaction() as connection:
        from web_backend.common import json_text

        prepared = service._prepare_publication(
            context.dataset, {context.key: source}, context.taxonomy
        )
        connection.execute(
            "UPDATE classification_units SET classification_json = ?, system_rerun_required = 1, quality_status = 'unusable' WHERE result_version_id = ?",
            (json_text(prepared["units"][0]["classification"]), version["version_id"]),
        )
        connection.execute(
            "UPDATE classification_result_records SET quality_status = 'unusable' WHERE result_version_id = ?",
            (version["version_id"],),
        )
    corrected = correct_group(
        service, version["version_id"], _record(context, version), _items(), "user-2"
    )
    assert current_inherited_results(context.database, corrected["version_id"]) == {}
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET status = 'running' WHERE id = ?",
            (context.segment_id,),
        )
    state = SegmentPublicationState(
        task_id=context.task_id,
        segment_id=context.segment_id,
        segment_status="completed_with_errors",
        progress_total=1,
        model_calls=2,
        cache_hits=0,
        checkpoint_path="test.json",
        legacy_result_version=2,
    )
    unchanged = service.publish_v1(
        dataset=context.dataset,
        results={context.key: source},
        taxonomy=context.taxonomy,
        segment_state=state,
    )
    assert unchanged["version_id"] == corrected["version_id"]
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET status = 'running' WHERE id = ?",
            (context.segment_id,),
        )
    successful = service.publish_v1(
        dataset=context.dataset,
        results=context.results,
        taxonomy=context.taxonomy,
        segment_state=state,
    )
    assert successful["version_id"] != corrected["version_id"]
    with context.database.connect() as connection:
        content = load_content(connection, successful["version_id"])
        manual = next(
            unit
            for unit in content["units"]
            if unit["classification_key"].startswith("manual:")
        )
        assert (
            manual["classification"]["semantic_units"][0]["opinion"] == "整体尺寸偏小"
        )
        assert not manual["system_rerun_required"]
