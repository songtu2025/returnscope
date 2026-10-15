"""隔离目录验证全量清理对异步导出缓存的覆盖与拒绝条件。"""

import json
from pathlib import Path

import pytest
from analysis_cleanup_helpers import cleanup_context as cleanup_context
from analysis_cleanup_helpers import lifecycle as lifecycle
from test_analysis_cleanup import _apply, _preview

from web_backend import analysis_cleanup
from web_backend.analysis_cleanup import CleanupApproval, apply_cleanup
from web_backend.analysis_cleanup_files import remove_cleanup_files
from web_backend.backup import create_backup
from web_backend.task_service import TaskService

SUFFIXES = (
    ".json",
    ".snapshot.gz",
    ".xlsx",
    ".json.tmp",
    ".snapshot.gz.tmp",
    ".xlsx.tmp",
)


def _export(context, status="ready"):
    folder = context.root / "result_exports"
    folder.mkdir()
    paths = [folder / ("a" * 64 + suffix) for suffix in SUFFIXES]
    for path in paths:
        path.write_bytes(b"synthetic-export-cache")
    paths[0].write_text(json.dumps({"status": status}), encoding="utf-8")
    return paths


def test_export_snapshots_outputs_and_orphans_are_temporary_cleanup_targets(
    cleanup_context,
):
    context = cleanup_context
    paths = _export(context)
    plan = _preview(context)
    assert plan.summary()["file_count"] == 11
    assert plan.summary()["temporary_file_count"] == len(paths)
    assert {
        item["path"]
        for item in plan.files
        if item["path"].startswith("result_exports/")
    } == {path.relative_to(context.root).as_posix() for path in paths}
    result, backup = _apply(context)
    assert result["complete"] is True
    assert all(not path.exists() for path in paths)
    assert backup.is_file()
    assert (context.root / "uploads/products.xlsx").is_file()
    assert all(
        context.root.joinpath(item["path"]).exists() is False for item in plan.files
    )


@pytest.mark.parametrize("status", ["queued", "running"])
def test_active_exports_block_cleanup_before_database_or_files_change(
    cleanup_context, status
):
    context = cleanup_context
    paths = _export(context, status)
    with context.database.connect() as connection:
        before = list(connection.iterdump())
    with pytest.raises(ValueError, match="导出任务尚未结束.*等待导出完成"):
        _apply(context)
    assert all(path.is_file() for path in paths)
    with context.database.connect() as connection:
        assert list(connection.iterdump()) == before


@pytest.mark.parametrize(
    "content", ["not-json", "[]", "{}", '{"status":"unknown"}', '{"status":[]}']
)
def test_damaged_export_manifest_is_not_assumed_idle(cleanup_context, content):
    paths = _export(cleanup_context)
    paths[0].write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="状态文件损坏"):
        _preview(cleanup_context)
    assert all(path.is_file() for path in paths)


def test_export_changes_invalidate_confirmed_preview(cleanup_context):
    context = cleanup_context
    paths = _export(context)
    plan = _preview(context)
    backup = create_backup(context.settings, context.root / "backups")
    paths[2].write_bytes(b"changed-synthetic-export")
    with pytest.raises(ValueError, match="范围已变化"):
        apply_cleanup(
            context.database.path,
            context.root,
            approval=CleanupApproval(plan.preview_hash, backup, "user-1", True),
        )
    assert all(path.is_file() for path in paths)


def test_export_activity_during_final_recheck_rolls_back_cleanup(
    cleanup_context, monkeypatch
):
    context = cleanup_context
    paths = _export(context)
    delete = analysis_cleanup._delete_records

    def activate_after_delete(connection, plan):
        delete(connection, plan)
        paths[0].write_text('{"status":"running"}', encoding="utf-8")

    monkeypatch.setattr(analysis_cleanup, "_delete_records", activate_after_delete)
    with pytest.raises(ValueError, match="导出任务尚未结束"):
        _apply(context)
    assert all(path.is_file() for path in paths)
    with context.database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 2


def test_export_paths_keep_existing_symlink_and_boundary_guards(
    cleanup_context, monkeypatch
):
    context = cleanup_context
    paths = _export(context)
    original = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink", lambda path: path == paths[0] or original(path)
    )
    with pytest.raises(ValueError, match="符号链接"):
        _preview(context)
    outside = context.root.parent / "outside-export.xlsx"
    outside.write_bytes(b"synthetic-retained")
    failed = remove_cleanup_files(context.root, [{"path": "../outside-export.xlsx"}])
    assert failed == ["../outside-export.xlsx"]
    assert outside.read_bytes() == b"synthetic-retained"


def test_removed_paused_listing_and_empty_parent_can_be_cleaned(cleanup_context):
    context = cleanup_context
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET status='paused' WHERE task_id='task-1'"
        )
        connection.execute("UPDATE tasks SET status='paused' WHERE id='task-1'")
    service = TaskService(context.database)
    task = service.get("task-1")
    removed = service.segment_action(
        task["id"],
        task["segments"][0]["segment_key"],
        "delete",
        "user-1",
        task["revision"],
    )
    assert removed["status"] == "empty"
    assert service.recycle.listings()["total"] == 1
    assert _preview(context).summary()["counts"]["tasks"] == 2
    result, _backup = _apply(context)
    assert result["complete"] is True
    assert service.recycle.listings()["total"] == 0


@pytest.mark.parametrize(
    "status,removed,removing",
    [
        ("paused", False, False),
        ("running", True, False),
        ("completed", True, True),
    ],
)
def test_cleanup_still_rejects_active_or_incomplete_listing_removal(
    cleanup_context, status, removed, removing
):
    context = cleanup_context
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET status=?,deleted_at=?,removal_requested_at=? WHERE task_id='task-1'",
            (
                status,
                "synthetic-removed" if removed else None,
                "synthetic-request" if removing else None,
            ),
        )
    with pytest.raises(ValueError, match="片段尚未结束"):
        _preview(context)
