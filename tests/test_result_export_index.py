"""核对导出快捷索引的数据库失效、并发和连接生命周期。"""

import gzip
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from test_result_export_jobs import context as context
from test_result_export_jobs import exports as exports

from web_backend.application_runtime import _create_lifespan
from web_backend.classification_result_service import ClassificationResultNotFound
from web_backend.classification_results import export_jobs
from web_backend.classification_results.export_jobs import ResultExportService
from web_backend.classification_results.result_export import SOURCE_FIELDS


def test_fast_hit_skips_full_processing(context, exports, monkeypatch):
    versions = [context.version["version_id"]]
    first = exports.create(versions)
    for target, name in (
        (exports.results, "capture_export"),
        (export_jobs.json, "dumps"),
        (export_jobs.hashlib, "sha256"),
        (export_jobs.gzip, "compress"),
    ):
        monkeypatch.setattr(target, name, Mock(side_effect=AssertionError(name)))
    assert exports.create(versions)["id"] == first["id"]


@pytest.mark.parametrize("field", ["comment", "product_name", "product_sku", "asin"])
def test_record_updates_never_reuse_old_snapshot(context, exports, field):
    versions = [context.version["version_id"]]
    first = exports.create(versions)
    with context.database.transaction() as connection:
        connection.execute(
            f"UPDATE classification_result_records SET {field}=?", ("合成新内容",)
        )
    second = exports.create(versions)
    assert second["id"] != first["id"]
    with gzip.open(
        exports._path(second["id"], ".snapshot.gz"), "rt", encoding="utf-8"
    ) as stream:
        snapshot = json.load(stream)
    assert all(row[field] == "合成新内容" for row in snapshot[0]["rows"])
    exports.run(second["id"])
    path, _ = exports.file(second["id"])
    book = load_workbook(path)
    rows = list(book["源明细"].values)
    column = next(name for name, source in SOURCE_FIELDS.items() if source == field)
    index = rows[0].index(column)
    assert all(row[index] == "合成新内容" for row in rows[1:])
    book.close()


def test_user_and_semantic_updates_invalidate_index(context, exports):
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_units SET classification_json=json_set(classification_json, '$.human_review_assessment.assessed_by', 'user-1')"
        )
    versions = [context.version["version_id"]]
    first = exports.create(versions)
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE users SET display_name='合成人工处理人' WHERE id='user-1'"
        )
    second = exports.create(versions)
    assert second["id"] != first["id"]
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_units SET classification_json=json_set(classification_json, '$.review_reasons', json('[\"合成复核原因\"]'))"
        )
    assert exports.create(versions)["id"] != second["id"]


def test_update_during_capture_is_not_registered_as_fast_hit(
    context, exports, monkeypatch
):
    original = exports.results.capture_export
    captured = []

    def capture(ids):
        snapshot = original(ids)
        captured.append(snapshot)
        if len(captured) == 1:
            with context.database.transaction() as connection:
                connection.execute(
                    "UPDATE classification_result_records SET comment='并发提交的新内容'"
                )
        return snapshot

    monkeypatch.setattr(exports.results, "capture_export", capture)
    versions = [context.version["version_id"]]
    first = exports.create(versions)
    second = exports.create(versions)
    assert first["id"] != second["id"]
    assert len(captured) == 2
    assert exports.create(versions)["id"] == second["id"]
    assert len(captured) == 2


def test_update_during_fast_lookup_forces_recapture(context, exports, monkeypatch):
    versions = [context.version["version_id"]]
    first = exports.create(versions)
    original = exports._reusable_job
    changed = False

    def lookup(job_id):
        nonlocal changed
        value = original(job_id)
        if not changed:
            changed = True
            with context.database.transaction() as connection:
                connection.execute(
                    "UPDATE classification_result_records SET comment='查询期间提交'"
                )
        return value

    monkeypatch.setattr(exports, "_reusable_job", lookup)
    assert exports.create(versions)["id"] != first["id"]


def test_monitor_reconnect_and_service_restart_recapture(context, exports, monkeypatch):
    versions = [context.version["version_id"]]
    first = exports.create(versions)
    capture = Mock(wraps=exports.results.capture_export)
    monkeypatch.setattr(exports.results, "capture_export", capture)
    exports.close()
    assert exports.create(versions)["id"] == first["id"]
    restarted = ResultExportService(context.service, exports.directory)
    try:
        assert restarted.create(versions)["id"] == first["id"]
    finally:
        restarted.close()
    assert capture.call_count == 2


def test_monitor_failure_falls_back_without_old_content(context, exports, monkeypatch):
    versions = [context.version["version_id"]]
    first = exports.create(versions)
    exports.close()
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_result_records SET comment='监测失败后的新内容'"
        )
    monkeypatch.setattr(
        exports._index, "_database_path", exports.directory / "missing.db"
    )
    assert exports.create(versions)["id"] != first["id"]


def test_index_capacity_and_rollback(context, exports, monkeypatch):
    versions = [context.version["version_id"]]
    first = exports.create(versions)
    token, _ = exports._index.lookup((export_jobs.EXPORT_FORMAT, *versions))
    with context.database.connect() as connection:
        connection.execute("BEGIN")
        connection.execute("UPDATE users SET display_name='回滚内容'")
        connection.rollback()
    assert exports._index.is_current(token)
    for number in range(70):
        exports._index.remember(("synthetic", str(number)), token, first["id"])
    assert len(exports._index._jobs) == 64
    capture = Mock(wraps=exports.results.capture_export)
    monkeypatch.setattr(exports.results, "capture_export", capture)
    assert exports.create(versions)["id"] == first["id"]
    capture.assert_called_once()


def test_format_change_and_deleted_version_cannot_hit(context, exports, monkeypatch):
    versions = [context.version["version_id"]]
    first = exports.create(versions)
    monkeypatch.setattr(export_jobs, "EXPORT_FORMAT", "synthetic-new-format")
    assert exports.create(versions)["id"] != first["id"]
    with context.database.transaction() as connection:
        connection.execute("DELETE FROM classification_result_records")
        connection.execute("DELETE FROM classification_units")
        connection.execute("UPDATE task_segments SET result_version_id=NULL")
        connection.execute("DELETE FROM classification_result_versions")
    with pytest.raises(ClassificationResultNotFound):
        exports.create(versions)


def test_parallel_warm_hits_share_job_without_recapture(context, exports, monkeypatch):
    versions = [context.version["version_id"]]
    first = exports.create(versions)
    capture = Mock(side_effect=AssertionError("热缓存不应读取完整快照"))
    monkeypatch.setattr(exports.results, "capture_export", capture)
    with ThreadPoolExecutor(max_workers=4) as executor:
        jobs = list(executor.map(exports.create, [versions] * 8))
    assert all(job["id"] == first["id"] for job in jobs)


@pytest.mark.parametrize("state", ["expired", "failed", "missing_file"])
def test_invalid_job_is_recaptured(context, exports, monkeypatch, state):
    versions = [context.version["version_id"]]
    first = exports.create(versions)
    if state == "missing_file":
        exports.run(first["id"])
        exports._path(first["id"], ".xlsx").unlink()
    else:
        job = exports._load(first["id"])
        job.update({"expires_at": 0} if state == "expired" else {"status": "failed"})
        exports._save(job)
    capture = Mock(wraps=exports.results.capture_export)
    monkeypatch.setattr(exports.results, "capture_export", capture)
    assert exports.create(versions)["status"] == "queued"
    capture.assert_called_once()


def test_other_process_commit_and_taxonomy_update_invalidate(context, exports):
    versions = [context.version["version_id"]]
    first = exports.create(versions)
    script = "import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);c.execute(\"UPDATE classification_result_records SET comment='other-process'\");c.commit();c.close()"
    subprocess.run(
        [sys.executable, "-c", script, str(context.database.path)],
        check=True,
        capture_output=True,
    )
    second = exports.create(versions)
    assert second["id"] != first["id"]
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_standard_versions SET snapshot_json=json_set(snapshot_json, '$.taxonomy.version', 'synthetic-taxonomy-update') WHERE id=(SELECT standard_version_id FROM classification_results WHERE id=?)",
            (context.version["result_id"],),
        )
    assert exports.create(versions)["id"] != second["id"]


def test_lifespan_closes_monitor_even_without_workers(context, exports):
    versions = [context.version["version_id"]]
    executor = ThreadPoolExecutor(max_workers=1)
    app = FastAPI(lifespan=_create_lifespan(False, (), executor, (exports.close,)))
    with TestClient(app):
        exports.create(versions)
        assert exports._index._connection is not None
    assert exports._index._connection is None
    assert not exports._index._jobs
