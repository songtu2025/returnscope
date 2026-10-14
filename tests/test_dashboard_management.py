import sqlite3
from pathlib import Path

import pytest
from test_dashboard_versions import _create_dashboard, _ready_result
from test_insight_reports import _complete_report, _service_context

from web_backend.dashboard_service import DashboardConflict
from web_backend.database_registered_migrations import migrate_report_removal
from web_backend.delivery_lifecycle import DeliveryLifecycleService


def test_dashboard_configuration_edit_preserves_identity_and_checks_revision(
    tmp_path: Path,
):
    _, version, service = _ready_result(tmp_path)
    _, dashboard = _create_dashboard(service, version["version_id"])
    filters = {"quality_status": ["ready", "review_required"]}
    plan = service.preflight([version["version_id"]], filters)
    payload = dict(
        expected_revision=dashboard["revision"],
        result_version_ids=[version["version_id"]],
        filters=filters,
        plan_hash=plan["plan_hash"],
        reason="调整统计范围",
        actor_id="user-1",
        name="更新后的看板",
    )
    changed = service.create_version(dashboard["id"], **payload)
    assert changed["id"] == dashboard["id"]
    assert changed["name"] == "更新后的看板"
    assert changed["revision"] == dashboard["revision"] + 1
    with pytest.raises(DashboardConflict):
        service.create_version(dashboard["id"], **payload)


def test_report_removal_and_restore_preserve_content_and_dashboard(tmp_path: Path):
    context, dashboard, reports, _ = _service_context(tmp_path)
    report = _complete_report(dashboard, reports)
    lifecycle = DeliveryLifecycleService(context.database)
    lifecycle.report(
        report["id"], revision=report["revision"], deleted=True, actor="user-1"
    )
    assert reports.list(dashboard["id"], dashboard["current_version_id"]) == []
    assert (
        len(
            reports.list(
                dashboard["id"], dashboard["current_version_id"], include_deleted=True
            )
        )
        == 1
    )
    lifecycle.report(
        report["id"], revision=report["revision"] + 1, deleted=False, actor="user-1"
    )
    restored = reports.get(report["id"])
    assert restored["content"] == report["content"]
    assert restored["status"] == "completed"


def test_report_migration_preserves_existing_content_and_is_repeatable():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE app_migrations (migration_id TEXT PRIMARY KEY, checksum TEXT NOT NULL, status TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE ai_insight_reports (id TEXT PRIMARY KEY, content TEXT)"
    )
    connection.execute(
        "INSERT INTO ai_insight_reports VALUES ('report-1', '原报告正文')"
    )
    migrate_report_removal(connection)
    migrate_report_removal(connection)
    row = connection.execute("SELECT * FROM ai_insight_reports").fetchone()
    assert row["content"] == "原报告正文"
    assert row["deleted_at"] is None
    assert row["revision"] == 1
    assert connection.execute("SELECT COUNT(*) FROM app_migrations").fetchone()[0] == 1
    connection.close()
