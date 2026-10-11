from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from return_import_helpers import (
    _create_task_input,
    _database_counts,
    _return_row,
    _write_returns,
)
from test_classification_result_pool import _seed_result_context

from web_backend.dataset_service import DatasetService


def _fail_import_audit(database) -> None:
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_import_return_audit
            BEFORE INSERT ON audit_logs
            WHEN NEW.action = 'import_returns'
            BEGIN
                SELECT RAISE(ABORT, 'injected import audit failure');
            END
            """
        )


def _assert_stored_files_exist(database) -> None:
    with database.connect() as connection:
        version_paths = connection.execute(
            "SELECT file_path FROM dataset_versions"
        ).fetchall()
        import_paths = connection.execute(
            "SELECT raw_file_path FROM dataset_imports"
        ).fetchall()
    assert all(Path(str(row[0])).is_file() for row in version_paths)
    assert all(Path(str(row[0])).is_file() for row in import_paths)


@pytest.mark.parametrize("mode", ["analyze_only"])
def test_new_return_import_rolls_back_when_audit_insert_fails(
    tmp_path: Path,
    mode: str,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / f"{mode}.csv"
    _write_returns(source, [_return_row("O-1", "偏小")])
    before = _database_counts(context.database)
    _fail_import_audit(context.database)

    with pytest.raises(sqlite3.IntegrityError, match="injected import audit failure"):
        service.import_returns(
            source_path=source,
            original_name=source.name,
            content_type="text/csv",
            mode=mode,
            actor_id="user-1",
        )

    assert _database_counts(context.database) == before
    assert not any((tmp_path / "imports").rglob("source.csv"))
    _assert_stored_files_exist(context.database)


def test_return_import_preserves_audit_actions_and_file_references(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    initial = tmp_path / "initial.csv"
    appended = tmp_path / "appended.csv"
    replaced = tmp_path / "replaced.csv"
    _write_returns(initial, [_return_row("O-1", "偏小")])
    _write_returns(appended, [_return_row("O-2", "不够保暖")])
    _write_returns(replaced, [_return_row("O-3", "抓握不好")])

    created = service.import_returns(
        source_path=initial,
        original_name=initial.name,
        content_type="text/csv",
        mode="analyze_only",
        actor_id="user-1",
    )
    dataset_id = str(created["dataset"]["id"])
    with context.database.connect() as connection:
        audit_rows = connection.execute(
            """
            SELECT action, after_json FROM audit_logs
            WHERE entity_type = 'dataset' AND entity_id = ?
            ORDER BY rowid
            """,
            (dataset_id,),
        ).fetchall()
    assert [row["action"] for row in audit_rows] == [
        "add_version",
        "create",
        "import_returns",
    ]
    import_audits = [
        json.loads(row["after_json"])
        for row in audit_rows
        if row["action"] == "import_returns"
    ]
    assert [item["mode"] for item in import_audits] == [
        "analyze_only",
    ]
    assert all(
        set(item)
        == {
            "import_id",
            "mode",
            "version_id",
            "raw_sha256",
            "imported_row_count",
            "skipped_row_count",
        }
        for item in import_audits
    )
    _assert_stored_files_exist(context.database)


def test_authoritative_duplicate_check_reuses_legacy_version(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "legacy-duplicate.csv"
    _write_returns(source, [_return_row("O-1", "偏小")])
    stale_inspection = service.inspect_return_import(source, source.name)
    created = _create_task_input(service, source)
    before = _database_counts(context.database)

    result = service.import_returns(
        source_path=source,
        original_name=source.name,
        content_type="text/csv",
        mode="analyze_only",
        actor_id="user-1",
        _inspection=stale_inspection,
    )

    assert result["duplicate"] is True
    assert result["version_id"] == created["versions"][0]["id"]
    assert _database_counts(context.database) == before


def test_blob_copy_failure_removes_temporary_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "blob-failure.csv"
    _write_returns(source, [_return_row("O-1", "偏小")])
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    def failing_copy(_source, destination, *_args, **_kwargs):
        Path(destination).write_bytes(b"partial")
        raise OSError("injected blob copy failure")

    monkeypatch.setattr(shutil, "copy2", failing_copy)
    with pytest.raises(OSError, match="injected blob copy failure"):
        service._ensure_blob(source, digest)

    blob_dir = tmp_path / "uploads" / "blobs"
    assert not (blob_dir / f"{digest}.csv").exists()
    assert not list(blob_dir.glob(f"{digest}.csv.blob_*"))


def test_concurrent_blob_writes_publish_complete_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "shared-blob.csv"
    _write_returns(
        source,
        [_return_row(f"O-{index}", f"问题-{index}") for index in range(100)],
    )
    content = source.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    destination = service._blob_path(digest, source.suffix)
    original_copy = shutil.copy2
    both_copied = threading.Barrier(3)
    publish_gate = threading.Event()

    def synchronized_copy(source_path, temporary, *args, **kwargs):
        result = original_copy(source_path, temporary, *args, **kwargs)
        both_copied.wait(timeout=10)
        if not publish_gate.wait(timeout=10):
            raise TimeoutError("等待发布 Blob 超时")
        return result

    monkeypatch.setattr(shutil, "copy2", synchronized_copy)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(service._ensure_blob, source, digest) for _ in range(2)
        ]
        both_copied.wait(timeout=10)
        try:
            assert not destination.exists()
            temporary_paths = list(
                destination.parent.glob(f"{destination.name}.blob_*")
            )
            assert len(temporary_paths) == 2
            assert all(path.read_bytes() == content for path in temporary_paths)
        finally:
            publish_gate.set()
        paths = [future.result(timeout=10) for future in futures]

    assert paths[0] == paths[1]
    assert paths[0].read_bytes() == content
    assert hashlib.sha256(paths[0].read_bytes()).hexdigest() == digest
    assert not list(paths[0].parent.glob(f"{paths[0].name}.blob_*"))
