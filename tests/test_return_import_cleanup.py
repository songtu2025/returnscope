from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from return_import_helpers import (
    _database_counts,
    _return_row,
    _write_returns,
)
from test_classification_result_pool import _seed_result_context

from web_backend.dataset_service import DatasetService
from web_backend.routers.datasets import create_dataset_router


def test_inspect_route_removes_temporary_file_after_unexpected_error(
    tmp_path: Path,
) -> None:
    class FailingDatasetService:
        def inspect_return_import(self, *_args, **_kwargs):
            raise RuntimeError("解析器异常")

    app = FastAPI()
    app.include_router(
        create_dataset_router(
            dataset_service=FailingDatasetService(),
            settings=SimpleNamespace(data_dir=tmp_path),
            current_user=lambda: {"id": "user-1"},
        )
    )

    with TestClient(app) as client, pytest.raises(RuntimeError, match="解析器异常"):
        client.post(
            "/api/return-imports/inspect",
            files={"file": ("returns.csv", b"a,b\n1,2", "text/csv")},
        )

    temporary_dir = tmp_path / "tmp" / "dataset-imports"
    assert not temporary_dir.exists() or not any(temporary_dir.iterdir())


@pytest.mark.parametrize("failure", ["staging_row", "source_file"])
def test_successful_staged_import_logs_cleanup_failure_without_payload(
    tmp_path: Path, monkeypatch, caplog, failure: str
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "SYNTHETIC-cleanup.csv"
    _write_returns(source, [_return_row("SYNTHETIC-ORDER", "SYNTHETIC-COMMENT")])
    inspection = service.inspect_return_import(source, source.name, actor_id="user-1")
    if failure == "staging_row":
        with context.database.transaction() as connection:
            connection.execute(
                """
                CREATE TRIGGER fail_staging_cleanup
                BEFORE DELETE ON dataset_import_staging
                BEGIN
                    SELECT RAISE(ABORT, 'SYNTHETIC-CONFIDENTIAL');
                END
                """
            )
    else:
        original_unlink = Path.unlink

        def fail_source_unlink(path, *args, **kwargs):
            if path == source:
                raise OSError("SYNTHETIC-CONFIDENTIAL")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", fail_source_unlink)
    result = service.import_staged_returns(
        inspection_id=str(inspection["inspection_id"]),
        actor_id="user-1",
        mode="analyze_only",
    )
    assert result["summary"]["imported_row_count"] == 1
    assert service.version_file(str(result["dataset"]["id"])) is not None
    records = [
        item
        for item in caplog.records
        if item.name == "web_backend.dataset_return_import"
    ]
    assert len(records) == 1
    assert "error_type=" in records[0].getMessage()
    assert records[0].exc_info is None
    assert "SYNTHETIC-CONFIDENTIAL" not in caplog.text
    assert str(source) not in caplog.text


def test_import_source_directory_cleanup_logs_only_error_type(
    tmp_path: Path, caplog
) -> None:
    directory = tmp_path / "SYNTHETIC-import"
    directory.mkdir()
    source = directory / "source.csv"
    source.write_text("SYNTHETIC-DATA", encoding="utf-8")
    extra = directory / "SYNTHETIC-CONFIDENTIAL"
    extra.write_text("SYNTHETIC-EXTRA", encoding="utf-8")
    DatasetService._cleanup_import_source(source)
    assert not source.exists()
    assert extra.exists()
    records = [
        item
        for item in caplog.records
        if item.name == "web_backend.dataset_return_versions"
    ]
    assert len(records) == 1
    assert records[0].getMessage() == "导入归档目录清理失败: error_type=OSError"
    assert records[0].exc_info is None
    assert "SYNTHETIC-CONFIDENTIAL" not in caplog.text
    assert str(directory) not in caplog.text


def test_import_source_file_cleanup_keeps_unlink_failure(
    monkeypatch, tmp_path: Path, caplog
) -> None:
    source = tmp_path / "SYNTHETIC-source.csv"

    def fail_unlink(*_args, **_kwargs):
        raise OSError("SYNTHETIC-UNLINK")

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    with pytest.raises(OSError, match="SYNTHETIC-UNLINK"):
        DatasetService._cleanup_import_source(source)
    assert not caplog.records


def test_return_import_copy_failure_cleans_unique_source_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "copy-failure.csv"
    _write_returns(source, [_return_row("O-1", "偏小")])
    before = _database_counts(context.database)
    original_copy = shutil.copy2

    def failing_copy(source_path, destination, *args, **kwargs):
        destination_path = Path(destination)
        if "imports" in destination_path.parts:
            destination_path.write_bytes(b"partial")
            raise OSError("injected copy failure")
        return original_copy(source_path, destination, *args, **kwargs)

    monkeypatch.setattr(shutil, "copy2", failing_copy)
    with pytest.raises(OSError, match="injected copy failure"):
        service.import_returns(
            source_path=source,
            original_name=source.name,
            content_type="text/csv",
            mode="analyze_only",
            actor_id="user-1",
        )

    assert _database_counts(context.database) == before
    assert not any((tmp_path / "imports").rglob("*"))
