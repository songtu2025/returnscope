from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_classification_result_pool import (
    _clone_publishable_segment,
    _seed_result_context,
)

from web_backend.agent_runner import AgentRunner
from web_backend.classification_result_service import (
    ClassificationResultService,
    ResultPublicationError,
)
from web_backend.common import json_text, json_value
from web_backend.legacy_result_backfill_service import (
    SYSTEM_ACTOR_ID,
    LegacyResultBackfillConflict,
    LegacyResultBackfillService,
)


def _legacy_completed(
    context: SimpleNamespace,
    checkpoint_path: Path,
    results: dict | None = None,
) -> None:
    AgentRunner._write_checkpoint(
        checkpoint_path,
        context.results if results is None else results,
    )
    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE task_segments
            SET status = 'completed', progress_current = progress_total,
                result_json_path = ?, result_publish_status = NULL,
                result_publish_error = NULL, completed_at = ?
            WHERE id = ?
            """,
            (
                str(checkpoint_path),
                "2026-08-12T00:02:00+00:00",
                context.segment_id,
            ),
        )
        connection.execute(
            "UPDATE tasks SET status = 'completed' WHERE id = ?",
            (context.task_id,),
        )


def _service(context: SimpleNamespace, tmp_path: Path):
    result_service = ClassificationResultService(context.database)
    runner = AgentRunner(
        context.database,
        SimpleNamespace(data_dir=tmp_path),
        SimpleNamespace(),
        result_service,
    )
    return LegacyResultBackfillService(context.database, runner), runner


def test_preview_and_apply_publish_legacy_v1_without_model_and_are_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _seed_result_context(tmp_path)
    _legacy_completed(context, tmp_path / "legacy-checkpoint.json")
    service, _runner = _service(context, tmp_path)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("历史结果回填不得调用模型")

    monkeypatch.setattr("web_backend.agent_runner.classify_comments", forbidden)
    preview = service.preview()
    assert preview["counts"] == {
        "ready": 1,
        "unavailable": 0,
        "incomplete": 0,
        "already_published": 0,
    }
    assert service.preview()["preview_hash"] == preview["preview_hash"]
    assert "classification_keys" not in json.dumps(preview, ensure_ascii=False)
    with context.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_result_versions"
            ).fetchone()[0]
            == 0
        )

    applied = service.apply(preview["preview_hash"])
    assert applied["counts"] == {"success": 1, "failed": 0, "skipped": 0}
    assert applied["success"][0]["version"] == 1
    assert applied["success"][0]["result_version_id"]
    replay = service.apply(preview["preview_hash"])
    assert replay["counts"] == {"success": 0, "failed": 0, "skipped": 1}

    with context.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_result_versions"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_result_records"
            ).fetchone()[0]
            == 3
        )
        segment = connection.execute(
            """
            SELECT result_publish_status, result_version_id, model_calls
            FROM task_segments WHERE id = ?
            """,
            (context.segment_id,),
        ).fetchone()
        event = connection.execute(
            """
            SELECT actor_id, data_json FROM task_events
            WHERE event_type = 'legacy_result_backfill_started'
            """
        ).fetchone()
        audit = connection.execute(
            """
            SELECT actor_id, after_json FROM audit_logs
            WHERE action = 'legacy_result_backfill_prepare'
            """
        ).fetchone()
    assert segment["result_publish_status"] == "published"
    assert segment["result_version_id"]
    assert segment["model_calls"] == 0
    assert event["actor_id"] == SYSTEM_ACTOR_ID
    assert json_value(event["data_json"], {})["preview_hash"] == preview["preview_hash"]
    assert audit["actor_id"] == SYSTEM_ACTOR_ID
    assert (
        json_value(audit["after_json"], {})["preview_hash"] == preview["preview_hash"]
    )


def test_preview_rejects_missing_incomplete_and_stale_checkpoint(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    missing_path = tmp_path / "missing.json"
    _legacy_completed(context, tmp_path / "temporary.json")
    missing_path.unlink(missing_ok=True)
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET result_json_path = ? WHERE id = ?",
            (str(missing_path), context.segment_id),
        )
    incomplete = _clone_publishable_segment(context, "incomplete")
    _legacy_completed(incomplete, tmp_path / "incomplete.json", {})
    service, _runner = _service(context, tmp_path)

    preview = service.preview()
    assert preview["counts"]["unavailable"] == 1
    assert preview["counts"]["incomplete"] == 1
    applied = service.apply(preview["preview_hash"])
    assert applied["counts"] == {"success": 0, "failed": 0, "skipped": 2}
    with context.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_result_versions"
            ).fetchone()[0]
            == 0
        )

    ready = _clone_publishable_segment(context, "stale")
    checkpoint = tmp_path / "stale.json"
    _legacy_completed(ready, checkpoint)
    stale_preview = service.preview()
    changed = {
        context.key: context.results[context.key].model_copy(
            update={"model_name": "changed-model"}
        )
    }
    AgentRunner._write_checkpoint(checkpoint, changed)
    with pytest.raises(LegacyResultBackfillConflict, match="已经变化"):
        service.apply(stale_preview["preview_hash"])


@pytest.mark.parametrize(
    "changed_field",
    ["task_listing", "snapshot_scope_mode", "segment_scope_json"],
)
def test_preview_hash_tracks_execution_scope_changes(
    tmp_path: Path,
    changed_field: str,
) -> None:
    context = _seed_result_context(tmp_path)
    _legacy_completed(context, tmp_path / f"scope-{changed_field}.json")
    service, _runner = _service(context, tmp_path)
    preview = service.preview()
    assert preview["counts"]["ready"] == 1

    with context.database.transaction() as connection:
        if changed_field == "task_listing":
            connection.execute(
                "UPDATE tasks SET listing = NULL WHERE id = ?",
                (context.task_id,),
            )
        elif changed_field == "snapshot_scope_mode":
            connection.execute(
                "UPDATE tasks SET snapshot_json = ? WHERE id = ?",
                (json_text({"scope": {"mode": "auto"}}), context.task_id),
            )
        else:
            connection.execute(
                "UPDATE task_segments SET scope_json = ? WHERE id = ?",
                (
                    json_text(
                        {
                            "listing": "L1",
                            "priority": 2,
                            "store": "SEEKWAY:US",
                        }
                    ),
                    context.segment_id,
                ),
            )

    refreshed = service.preview()
    assert refreshed["preview_hash"] != preview["preview_hash"]
    with pytest.raises(LegacyResultBackfillConflict, match="已经变化"):
        service.apply(preview["preview_hash"])
    with context.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_result_versions"
            ).fetchone()[0]
            == 0
        )


def test_apply_failure_does_not_block_later_segment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _seed_result_context(tmp_path)
    second = _clone_publishable_segment(context, "second")
    _legacy_completed(context, tmp_path / "first.json")
    _legacy_completed(second, tmp_path / "second.json")
    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE task_segments
            SET status = 'completed_with_errors', result_publish_status = 'legacy'
            WHERE id = ?
            """,
            (second.segment_id,),
        )
    service, runner = _service(context, tmp_path)
    original_publish = runner.result_service.publish_v1

    def fail_first(**kwargs):
        if kwargs["segment_id"] == context.segment_id:
            raise ResultPublicationError("模拟单片段发布失败")
        return original_publish(**kwargs)

    monkeypatch.setattr(runner.result_service, "publish_v1", fail_first)
    preview = service.preview()
    applied = service.apply(preview["preview_hash"])

    assert applied["counts"] == {"success": 1, "failed": 1, "skipped": 0}
    assert applied["success"][0]["segment_id"] == second.segment_id
    assert applied["failed"][0]["segment_id"] == context.segment_id
    with context.database.connect() as connection:
        first = connection.execute(
            "SELECT result_publish_status FROM task_segments WHERE id = ?",
            (context.segment_id,),
        ).fetchone()
        second_row = connection.execute(
            """
            SELECT result_publish_status, result_version_id
            FROM task_segments WHERE id = ?
            """,
            (second.segment_id,),
        ).fetchone()
        assert (
            connection.execute(
                """
            SELECT COUNT(*) FROM audit_logs
            WHERE action = 'legacy_result_backfill_prepare'
            """
            ).fetchone()[0]
            == 2
        )
    assert first["result_publish_status"] == "failed"
    assert second_row["result_publish_status"] == "published"
    assert second_row["result_version_id"]


def test_backfill_cli_outputs_json_and_requires_preview_hash(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    _legacy_completed(context, tmp_path / "cli-checkpoint.json")
    environment = {
        **os.environ,
        "WEBAPP_DATA_DIR": str(tmp_path),
        "WEBAPP_DATABASE_PATH": str(context.database.path),
        "WEBAPP_PRODUCTION": "false",
    }
    script = Path("scripts/backfill_legacy_classification_results.py")
    preview_run = subprocess.run(
        [sys.executable, str(script)],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert preview_run.returncode == 0
    preview = json.loads(preview_run.stdout)
    assert preview["mode"] == "preview"
    assert preview["counts"]["ready"] == 1

    missing_hash = subprocess.run(
        [sys.executable, str(script), "--apply"],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing_hash.returncode == 2
    assert json.loads(missing_hash.stdout)["error"]

    apply_run = subprocess.run(
        [
            sys.executable,
            str(script),
            "--apply",
            "--preview-hash",
            preview["preview_hash"],
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert apply_run.returncode == 0
    assert json.loads(apply_run.stdout)["counts"]["success"] == 1
