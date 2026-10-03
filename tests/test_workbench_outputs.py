from pathlib import Path

import pytest
from test_classification_result_pool import _publish, _seed_result_context
from test_insight_reports import _complete_report, _service_context

from web_backend.dashboard_service import DashboardService
from web_backend.operations_service import WorkbenchService


def test_workbench_distinguishes_derived_results_and_dashboards(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    first = _publish(context)
    first_id = str(first["version_id"])
    with context.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO classification_result_versions(
                id, result_id, source_segment_id, version_no, content_hash,
                quality_status, publish_status, unit_count, record_count,
                parent_version_id, version_reason, created_by, created_at,
                published_at
            ) SELECT 'derived-v2', result_id, source_segment_id, 2, 'hash-v2',
                     'ready', 'published', unit_count, record_count, id,
                     '人工复核发布', 'user-1', '2026-08-12T02:00:00+00:00',
                     '2026-08-12T02:00:00+00:00'
              FROM classification_result_versions WHERE id = ?
            """,
            (first_id,),
        )
        connection.execute(
            """
            INSERT INTO classification_result_versions(
                id, result_id, source_segment_id, version_no, content_hash,
                quality_status, publish_status, unit_count, record_count,
                parent_version_id, version_reason, created_by, created_at,
                published_at
            ) SELECT 'review-v3', result_id, source_segment_id, 3, 'hash-v3',
                     'review_required', 'published', unit_count, record_count,
                     id, '待复核', 'user-1', '2026-08-12T03:00:00+00:00',
                     '2026-08-12T03:00:00+00:00'
              FROM classification_result_versions WHERE id = 'derived-v2'
            """
        )
    dashboard_service = DashboardService(context.database)
    plan = dashboard_service.preflight([first_id], {})
    dashboard = dashboard_service.create(
        name="确定性看板",
        description="",
        result_version_ids=[first_id],
        filters={},
        plan_hash=plan["plan_hash"],
        reason="创建看板",
        actor_id="user-1",
    )

    summary = WorkbenchService(context.database).summary(limit=10)
    types = [item["type"] for item in summary["recent_outputs"]]
    assert "classification_result" in types
    assert "derived_result" in types
    assert "dashboard" in types
    assert all(item["version_id"] != "review-v3" for item in summary["recent_outputs"])
    derived = next(
        item for item in summary["recent_outputs"] if item["type"] == "derived_result"
    )
    assert derived["version_id"] == "derived-v2"
    dashboard_output = next(
        item for item in summary["recent_outputs"] if item["type"] == "dashboard"
    )
    assert dashboard_output["object_id"] == dashboard["id"]
    assert dashboard_output["version_id"] == dashboard["current_version_id"]


@pytest.mark.parametrize("limit", [1, 2, 20])
def test_recent_outputs_use_type_order_for_equal_time_before_truncation(
    tmp_path: Path, limit: int
) -> None:
    context, dashboard, reports, _ = _service_context(tmp_path)
    report = _complete_report(dashboard, reports)
    assert report["status"] == "completed"
    stamp = "2026-08-12T02:00:00+00:00"
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_result_versions SET published_at=?", (stamp,)
        )
        connection.execute("UPDATE analysis_dashboards SET updated_at=?", (stamp,))
        connection.execute(
            "UPDATE ai_insight_report_versions SET published_at=?", (stamp,)
        )
    summary = WorkbenchService(context.database).summary(limit=limit)
    outputs = summary["recent_outputs"]
    assert [item["type"] for item in outputs] == [
        "classification_result",
        "dashboard",
        "insight_report",
    ][:limit]
    assert all(item["updated_at"] == stamp for item in outputs)
    if limit >= 3:
        published_report = outputs[-1]
        assert published_report["object_id"] == report["id"]
        assert published_report["version_no"] == 1
        assert (
            published_report["target"]["version_id"]
            == dashboard["version"]["version_id"]
        )
        assert published_report["target"]["report_id"] == report["id"]
