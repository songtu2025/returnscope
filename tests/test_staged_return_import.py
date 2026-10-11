from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from return_import_helpers import (
    _database_counts,
    _return_row,
    _write_returns,
)
from test_classification_result_pool import _seed_result_context

from web_backend.dataset_service import DatasetService


def test_staged_return_import_enforces_owner_retry_and_single_use(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "staged.csv"
    _write_returns(source, [_return_row("O-1", "偏小")])
    inspection = service.inspect_return_import(
        source,
        source.name,
        actor_id="user-1",
    )
    inspection_id = str(inspection["inspection_id"])

    try:
        service.import_staged_returns(
            inspection_id=inspection_id,
            actor_id="user-2",
            mode="analyze_only",
        )
    except ValueError as exc:
        assert "无权" in str(exc)
    else:
        raise AssertionError("必须拒绝其他用户的检查记录")

    try:
        service.import_staged_returns(
            inspection_id=inspection_id,
            actor_id="user-1",
            mode="invalid",
        )
    except ValueError as exc:
        assert "仅支持" in str(exc)
    else:
        raise AssertionError("无效导入应失败")
    assert source.exists()

    result = service.import_staged_returns(
        inspection_id=inspection_id,
        actor_id="user-1",
        mode="analyze_only",
    )
    assert result["summary"]["imported_row_count"] == 1
    assert not source.exists()
    try:
        service.import_staged_returns(
            inspection_id=inspection_id,
            actor_id="user-1",
            mode="analyze_only",
        )
    except ValueError as exc:
        assert "过期" in str(exc)
    else:
        raise AssertionError("已导入的检查记录不能重复使用")


def test_staged_cleanup_keeps_expired_import_while_processing(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "processing.csv"
    _write_returns(source, [_return_row("O-1", "偏小")])
    inspection = service.inspect_return_import(
        source,
        source.name,
        actor_id="user-1",
    )
    inspection_id = str(inspection["inspection_id"])
    with context.database.transaction(immediate=True) as connection:
        connection.execute(
            """
            UPDATE dataset_import_staging
            SET expires_at = '2000-01-01T00:00:00+00:00',
                consumed_at = '2026-09-07T00:00:00+00:00'
            WHERE id = ?
            """,
            (inspection_id,),
        )

    service._cleanup_staged_imports()

    with context.database.connect() as connection:
        staged = connection.execute(
            "SELECT id FROM dataset_import_staging WHERE id = ?",
            (inspection_id,),
        ).fetchone()
    assert staged is not None
    assert source.exists()


@pytest.mark.parametrize("mode", ["analyze_only"])
def test_staged_retry_after_response_failure_is_idempotent(
    tmp_path: Path,
    monkeypatch,
    mode: str,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / f"staged-{mode}.csv"
    _write_returns(source, [_return_row("O-2", "不够保暖")])
    inspection = service.inspect_return_import(
        source,
        source.name,
        actor_id="user-1",
    )
    inspection_id = str(inspection["inspection_id"])
    raw_sha256 = str(inspection["raw_sha256"])
    original_get = service.get
    failed = False

    def fail_first_get_after_commit(*args, **kwargs):
        nonlocal failed
        with context.database.connect() as connection:
            committed = connection.execute(
                "SELECT 1 FROM dataset_imports WHERE raw_sha256 = ? LIMIT 1",
                (raw_sha256,),
            ).fetchone()
        if committed is not None and not failed:
            failed = True
            raise RuntimeError("injected response failure")
        return original_get(*args, **kwargs)

    monkeypatch.setattr(service, "get", fail_first_get_after_commit)
    with pytest.raises(RuntimeError, match="injected response failure"):
        service.import_staged_returns(
            inspection_id=inspection_id,
            actor_id="user-1",
            mode=mode,
        )

    with context.database.connect() as connection:
        committed_import = dict(
            connection.execute(
                """
                SELECT id, dataset_id, resulting_version_id, raw_file_path,
                       raw_sha256
                FROM dataset_imports WHERE raw_sha256 = ?
                """,
                (raw_sha256,),
            ).fetchone()
        )
        staging = connection.execute(
            "SELECT consumed_at FROM dataset_import_staging WHERE id = ?",
            (inspection_id,),
        ).fetchone()
    assert staging["consumed_at"] is None
    assert Path(committed_import["raw_file_path"]).is_file()
    counts_after_commit = _database_counts(context.database)

    retried = service.import_staged_returns(
        inspection_id=inspection_id,
        actor_id="user-1",
        mode=mode,
    )

    assert retried["duplicate"] is True
    assert retried["version_id"] == committed_import["resulting_version_id"]
    assert retried["dataset"]["id"] == committed_import["dataset_id"]
    assert _database_counts(context.database) == counts_after_commit
    with context.database.connect() as connection:
        persisted_imports = connection.execute(
            """
            SELECT id, raw_file_path FROM dataset_imports
            WHERE raw_sha256 = ?
            """,
            (raw_sha256,),
        ).fetchall()
        assert (
            connection.execute(
                "SELECT 1 FROM dataset_import_staging WHERE id = ?",
                (inspection_id,),
            ).fetchone()
            is None
        )
    assert len(persisted_imports) == 1
    assert persisted_imports[0]["id"] == committed_import["id"]
    assert persisted_imports[0]["raw_file_path"] == committed_import["raw_file_path"]
    assert Path(str(persisted_imports[0]["raw_file_path"])).is_file()
