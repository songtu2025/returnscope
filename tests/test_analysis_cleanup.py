"""用现有合成业务链验证清理范围、拒绝条件和恢复能力。"""

from __future__ import annotations

import hashlib
import sqlite3
import zipfile

import pytest
from analysis_cleanup_helpers import cleanup_context as cleanup_context
from analysis_cleanup_helpers import lifecycle as lifecycle

from web_backend import analysis_cleanup
from web_backend.analysis_cleanup import CleanupApproval, apply_cleanup, preview_cleanup
from web_backend.backup import create_backup, restore_backup


def _preview(context):
    return preview_cleanup(context.database.path, context.root)


def _apply(context, **changes):
    plan = _preview(context)
    backup = create_backup(context.settings, context.root / "backups")
    arguments = {
        "preview_hash": plan.preview_hash,
        "backup_path": backup,
        "actor_id": "user-1",
        "app_stopped": True,
        **changes,
    }
    return apply_cleanup(
        context.database.path,
        context.root,
        approval=CleanupApproval(**arguments),
    ), backup


def test_preview_is_read_only_and_covers_derived_results(cleanup_context):
    context = cleanup_context
    before = hashlib.sha256(context.database.path.read_bytes()).hexdigest()
    plan = _preview(context)
    assert plan.summary()["counts"]["classification_result_versions"] == 3
    assert plan.summary()["counts"]["review_revisions"] == 1
    assert plan.summary()["counts"]["ai_insight_reports"] == 1
    assert plan.summary()["file_count"] == 5
    assert before == hashlib.sha256(context.database.path.read_bytes()).hexdigest()
    assert _preview(context).preview_hash == plan.preview_hash


def test_apply_clears_mysql_and_feedback_inputs_preserves_products_and_restores_backup(
    cleanup_context,
):
    context = cleanup_context
    protected = (
        "users",
        "api_connections",
        "api_config_versions",
        "classification_standards",
        "app_migrations",
    )
    with context.database.connect() as connection:
        before = {
            table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")]
            for table in protected
        }
    result, backup = _apply(context)
    assert result["complete"] is True
    with context.database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_results"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute("SELECT kind FROM datasets").fetchall()[0][0]
            == "products"
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM analysis_dashboards").fetchone()[0]
            == 0
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM review_revisions").fetchone()[0]
            == 0
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM ai_insight_reports").fetchone()[0]
            == 0
        )
        assert list(connection.execute("PRAGMA foreign_key_check")) == []
        for table in protected:
            assert [
                tuple(row) for row in connection.execute(f"SELECT * FROM {table}")
            ] == before[table]
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE entity_type = 'analysis_cleanup'"
            ).fetchone()[0]
            == 1
        )
    assert not (context.root / "results/task-1/old-result.xlsx").exists()
    assert not (context.root / "cache/task-1-config-1.jsonl").exists()
    assert not (
        context.root / "cache/classification-standard-validation.jsonl"
    ).exists()
    assert (context.root / "uploads/products.xlsx").exists()
    assert not (context.root / "uploads/returns.csv").exists()
    restore_backup(context.settings, backup, context.root / "restore-backups")
    with context.database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 2
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_result_versions"
            ).fetchone()[0]
            == 3
        )
    assert (context.root / "results/task-1/old-result.xlsx").exists()


@pytest.mark.parametrize(
    "table, column, value, message",
    [
        ("tasks", "status", "running", "任务尚未结束"),
        ("task_segments", "status", "queued", "片段尚未结束"),
        ("ai_insight_reports", "status", "running", "洞察尚未结束"),
    ],
)
def test_rejects_active_work(cleanup_context, table, column, value, message):
    with cleanup_context.database.transaction() as connection:
        connection.execute(f"UPDATE {table} SET {column} = ?", (value,))
    with pytest.raises(ValueError, match=message):
        _preview(cleanup_context)


@pytest.mark.parametrize("change", ["review", "file", "backup"])
def test_rejects_stale_preview_without_deleting(cleanup_context, change):
    context = cleanup_context
    plan = _preview(context)
    backup = create_backup(context.settings, context.root / "backups")
    if change in {"review", "backup"}:
        with context.database.transaction() as connection:
            connection.execute("UPDATE review_records SET revision = revision + 1")
    else:
        (context.root / "results/task-1/analysis.xlsx").write_bytes(b"changed")
    if change == "backup":
        plan = _preview(context)
    message = "备份数据" if change == "backup" else "范围已变化"
    with pytest.raises(ValueError, match=message):
        apply_cleanup(
            context.database.path,
            context.root,
            approval=CleanupApproval(plan.preview_hash, backup, "user-1", True),
        )
    assert (context.root / "results/task-1/old-result.xlsx").exists()


@pytest.mark.parametrize(
    "changes, message",
    [({"app_stopped": False}, "应用已停止"), ({"actor_id": "user-2"}, "管理员")],
)
def test_requires_operator_and_stopped_app(cleanup_context, changes, message):
    with pytest.raises(ValueError, match=message):
        _apply(cleanup_context, **changes)


def test_database_error_rolls_back_and_keeps_files(cleanup_context):
    context = cleanup_context
    with context.database.transaction() as connection:
        connection.execute(
            "CREATE TRIGGER reject_task_cleanup BEFORE DELETE ON tasks BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="synthetic failure"):
        _apply(context)
    with context.database.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM review_revisions").fetchone()[0]
            == 1
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM analysis_dashboards").fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_result_versions"
            ).fetchone()[0]
            == 3
        )
    assert (context.root / "results/task-1/old-result.xlsx").exists()


def test_reports_partial_file_failure(cleanup_context, monkeypatch):
    monkeypatch.setattr(
        analysis_cleanup,
        "remove_cleanup_files",
        lambda *_: ["results/task-1/analysis.xlsx"],
    )
    result, _ = _apply(cleanup_context)
    assert result["database_applied"] is True
    assert result["complete"] is False
    assert result["failed_files"] == ["results/task-1/analysis.xlsx"]


@pytest.mark.parametrize("target", ["outside", "shared"])
def test_rejects_unsafe_or_shared_result_files(cleanup_context, target):
    context = cleanup_context
    path = (
        context.root.parent / "outside.xlsx"
        if target == "outside"
        else context.root / "results/task-1/analysis.xlsx"
    )
    with context.database.transaction() as connection:
        if target == "outside":
            connection.execute(
                "UPDATE tasks SET result_file_path = ? WHERE id = 'task-1'",
                (str(path),),
            )
        else:
            connection.execute(
                "UPDATE dataset_versions SET file_path = ? WHERE dataset_id = 'dataset-products'",
                (str(path),),
            )
    with pytest.raises(ValueError, match="越界或仍被保留"):
        _preview(context)


def test_rejects_backup_with_changed_file_content(cleanup_context):
    context = cleanup_context
    plan = _preview(context)
    backup = create_backup(context.settings, context.root / "backups")
    changed = context.root / "backups/changed.zip"
    with zipfile.ZipFile(backup) as source, zipfile.ZipFile(changed, "w") as target:
        for name in source.namelist():
            data = source.read(name)
            if name == "results/task-1/old-result.xlsx":
                data = b"x" * len(data)
            target.writestr(name, data)
    with pytest.raises(ValueError, match="备份产物内容"):
        apply_cleanup(
            context.database.path,
            context.root,
            approval=CleanupApproval(plan.preview_hash, changed, "user-1", True),
        )
    assert (context.root / "results/task-1/old-result.xlsx").exists()


def test_cli_defaults_to_preview_and_requires_backup(
    cleanup_context, monkeypatch, capsys
):
    from scripts.cleanup_analysis_data import main

    context = cleanup_context
    arguments = [
        "cleanup_analysis_data.py",
        "--database",
        str(context.database.path),
        "--data-dir",
        str(context.root),
        "--all-analysis",
    ]
    before = context.database.path.read_bytes()
    monkeypatch.setattr("sys.argv", arguments)
    assert main() == 0
    assert '"preview_hash"' in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", [*arguments, "--apply"])
    assert main() == 2
    assert "完整备份" in capsys.readouterr().out
    assert context.database.path.read_bytes() == before
