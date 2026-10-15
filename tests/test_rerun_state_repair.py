from dataclasses import replace
from pathlib import Path

import pytest
from test_dashboard_versions import _create_dashboard
from test_result_version_reviews import _publish_review_required
from test_web_backup import _settings

from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_results import rerun_state_repair as repair
from web_backend.common import json_text
from web_backend.dashboard_service import DashboardService
from web_backend.task_service import TaskService


def _legacy_state(tmp_path: Path, code: str = "MODEL_RESULT_MISMATCH"):
    context, version = _publish_review_required(tmp_path)
    classification = context.results[context.key].model_dump(mode="json")
    classification.update(
        status="MANUAL_REVIEW",
        review_reasons=["两次模型的语义结果不一致"],
        review_diagnostics=[{"code": code, "action": "SYSTEM_RERUN"}],
    )
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_units SET classification_json = ?, "
            "quality_status = 'unusable', system_rerun_required = 1 WHERE result_version_id = ?",
            (json_text(classification), version["version_id"]),
        )
        connection.execute(
            "UPDATE classification_result_records SET quality_status = 'unusable' WHERE result_version_id = ?",
            (version["version_id"],),
        )
        connection.execute(
            "UPDATE classification_result_versions SET quality_status = 'unusable' WHERE id = ?",
            (version["version_id"],),
        )
        connection.execute(
            "UPDATE task_segments SET status = 'completed_with_errors', result_quality_status = 'unusable' WHERE id = ?",
            (context.segment_id,),
        )
    return context, version, json_text(classification)


def test_preview_does_not_write_and_apply_syncs_filters_task_and_dashboard(
    tmp_path: Path,
):
    context, version, original = _legacy_state(tmp_path)
    database = context.database
    dashboards = DashboardService(database)
    _, dashboard = _create_dashboard(
        dashboards, version["version_id"], {"quality_status": ["unusable"]}
    )
    before = dashboard["version"]["version_id"]
    assert repair.repair_states(database) == {"units": 1, "versions": 1}
    results = ClassificationResultService(database)
    assert (
        results.record_groups(version["version_id"], system_rerun_required="true")[
            "total"
        ]
        == 2
    )
    assert repair.repair_states(database, apply=True) == {"units": 1, "versions": 1}
    assert (
        results.record_groups(version["version_id"], system_rerun_required="true")[
            "total"
        ]
        == 0
    )
    assert (
        results.record_groups(version["version_id"], quality_status="review_required")[
            "total"
        ]
        == 2
    )
    assert (
        results.record_groups(version["version_id"], quality_status="unusable")["total"]
        == 0
    )
    task = TaskService(database).get(context.task_id)
    segment = next(
        item for item in task["segments"] if item["id"] == context.segment_id
    )
    assert segment["system_failure_count"] == 0
    assert segment["system_retry_available"] is False
    assert segment["pending_review_count"] == 3
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT classification_json FROM classification_units"
            ).fetchone()[0]
            == original
        )
        assert (
            connection.execute(
                "SELECT quality_status FROM classification_result_versions WHERE id = ?",
                (version["version_id"],),
            ).fetchone()[0]
            == "review_required"
        )
    current = dashboards.get(dashboard["id"])
    assert current["version"]["version_id"] != before
    assert current["version"]["filters"] == {"quality_status": ["unusable"]}
    assert (
        dashboards.records(dashboard["id"], current["version"]["version_id"])["total"]
        == 0
    )
    assert repair.repair_states(database, apply=True) == {"units": 0, "versions": 0}
    assert dashboards.get(dashboard["id"])["revision"] == current["revision"]
    with pytest.raises(ValueError, match="没有需要重试的失败项"):
        TaskService(database).retry_segment(
            context.task_id, "footwear", "user-1", task["revision"], ""
        )


@pytest.mark.parametrize(
    "code",
    ["MODEL_RUN_TIMEOUT", "SECONDARY_MODEL_CALL_FAILED", "SECONDARY_RESULT_INVALID"],
)
def test_real_technical_failure_is_not_cleared(tmp_path: Path, code: str):
    context, version, _original = _legacy_state(tmp_path, code)
    repair.repair_states(context.database, apply=True)
    groups = ClassificationResultService(context.database).record_groups(
        version["version_id"], system_rerun_required="true"
    )
    assert groups["total"] == 2
    assert all(
        item["record"]["quality_status"] == "unusable" for item in groups["items"]
    )


def test_failed_dashboard_refresh_rolls_back_marks_and_migration(
    tmp_path: Path, monkeypatch
):
    context, version, _original = _legacy_state(tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("合成看板刷新失败")

    monkeypatch.setattr(repair, "refresh_related_dashboards", fail)
    with pytest.raises(RuntimeError, match="合成看板刷新失败"):
        repair.repair_states(context.database, apply=True)
    with context.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT system_rerun_required FROM classification_units"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM app_migrations WHERE migration_id = ?",
                (repair.MIGRATION_ID,),
            ).fetchone()[0]
            == 0
        )
    assert (
        ClassificationResultService(context.database).record_groups(
            version["version_id"], quality_status="unusable"
        )["total"]
        == 2
    )


def test_cli_requires_stop_and_verified_backup_can_restore_old_marks(
    tmp_path: Path, monkeypatch
):
    context, _version, _original = _legacy_state(tmp_path)
    settings = replace(
        _settings(tmp_path), data_dir=tmp_path, database_path=context.database.path
    )
    monkeypatch.setenv("WEBAPP_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(repair.Settings, "from_env", lambda: settings)
    monkeypatch.setattr("sys.argv", ["repair"])
    repair.main()
    assert not list(tmp_path.rglob("seekway-backup-*.zip"))
    monkeypatch.setattr("sys.argv", ["repair", "--apply"])
    with pytest.raises(SystemExit):
        repair.main()
    monkeypatch.setattr("sys.argv", ["repair", "--apply", "--app-stopped"])
    repair.main()
    backup = next(tmp_path.rglob("seekway-backup-*.zip"))
    repair.verify_backup(backup)
    from web_backend.backup import restore_backup

    restore_backup(settings, backup)
    with context.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT system_rerun_required FROM classification_units"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM app_migrations WHERE migration_id = ?",
                (repair.MIGRATION_ID,),
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize("checksum_matches", [True, False])
def test_existing_execution_does_not_hide_preview_or_allow_reapplication(
    tmp_path: Path, checksum_matches: bool
):
    context, version, _original = _legacy_state(tmp_path)
    database = context.database
    assert repair.repair_states(database, apply=True) == {"units": 1, "versions": 1}
    with database.transaction() as connection:
        # 模拟执行完成后出现新的历史差异，不能借预览重新执行旧修复。
        connection.execute(
            "UPDATE classification_units SET quality_status='unusable', system_rerun_required=1 WHERE result_version_id=?",
            (version["version_id"],),
        )
        if not checksum_matches:
            connection.execute(
                "UPDATE app_migrations SET checksum='synthetic-previous-checksum' WHERE migration_id=?",
                (repair.MIGRATION_ID,),
            )
    with database.connect() as connection:
        before = list(connection.iterdump())
    assert repair.repair_states(database) == {"units": 1, "versions": 1}
    assert repair.repair_states(database) == {"units": 1, "versions": 1}
    if checksum_matches:
        assert repair.repair_states(database, apply=True) == {"units": 0, "versions": 0}
    else:
        with pytest.raises(ValueError, match="校验不一致"):
            repair.repair_states(database, apply=True)
    with database.connect() as connection:
        assert list(connection.iterdump()) == before
