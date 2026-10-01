from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from test_classification_result_pool import _publish, _seed_result_context
from test_database_migrations import _settings
from test_result_version_reviews import _publish_review_required

from web_backend.backup import restore_backup
from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_unit_semantics import (
    SEMANTIC_MIGRATION,
    SEMANTIC_MIGRATION_CHECKSUM,
)
from web_backend.review_service import ReviewService
from web_backend.upgrade_database import upgrade_database


def _assert_projection(connection: sqlite3.Connection, version_id: str) -> None:
    expected = connection.execute(
        """
        SELECT u.result_version_id, u.classification_key, unit.key,
               json_extract(unit.value, '$.subject'),
               json_extract(unit.value, '$.label_code'),
               json_extract(unit.value, '$.part'),
               json_extract(unit.value, '$.opinion'),
               json_extract(unit.value, '$.evidence')
        FROM classification_units u
        JOIN json_each(u.classification_json, '$.semantic_units') unit
        WHERE u.result_version_id = ? ORDER BY u.classification_key, unit.key
        """,
        (version_id,),
    ).fetchall()
    actual = connection.execute(
        """
        SELECT * FROM classification_unit_semantics WHERE result_version_id = ?
        ORDER BY classification_key, semantic_index
        """,
        (version_id,),
    ).fetchall()
    assert expected
    assert [tuple(row) for row in actual] == [tuple(row) for row in expected]


def _remove_projection(connection: sqlite3.Connection) -> None:
    connection.execute("DROP TABLE classification_unit_semantics")
    connection.execute(
        "DELETE FROM app_migrations WHERE migration_id = ?", (SEMANTIC_MIGRATION,)
    )


def test_publication_and_review_keep_independent_semantic_versions(
    tmp_path: Path,
) -> None:
    context, base = _publish_review_required(tmp_path)
    service = ReviewService(context.database)
    batch = service.create_batch(base["version_id"], "user-1", "核对语义投影")
    review = service.batch_records(batch["id"])["items"][0]
    service.update_batch_record(
        batch["id"],
        review["id"],
        review["revision"],
        "user-1",
        "FIT_TOO_LARGE_U1",
        "人工确认偏大",
    )
    derived = service.publish_batch(
        batch["id"],
        service.get_batch(batch["id"])["revision"],
        "user-1",
        "发布修正语义",
    )
    with context.database.connect() as connection:
        for version in (base, derived):
            _assert_projection(connection, version["version_id"])
        codes = {
            row["result_version_id"]: row["label_code"]
            for row in connection.execute("SELECT * FROM classification_unit_semantics")
        }
        assert codes[base["version_id"]] == "FIT_TOO_SMALL_U1"
        assert codes[derived["version_id"]] == "FIT_TOO_LARGE_U1"


def test_failed_review_publication_rolls_back_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, base = _publish_review_required(tmp_path)
    results = ClassificationResultService(context.database)
    service = ReviewService(context.database, results)
    batch = service.create_batch(base["version_id"], "user-1", "核对回滚")
    review = service.batch_records(batch["id"])["items"][0]
    service.update_batch_record(
        batch["id"],
        review["id"],
        review["revision"],
        "user-1",
        "FIT_TOO_LARGE_U1",
        "核对发布失败",
    )

    def fail_records(*args: object, **kwargs: object) -> None:
        raise RuntimeError("模拟明细写入后失败")

    monkeypatch.setattr(results, "_insert_records", fail_records)
    with pytest.raises(RuntimeError, match="模拟明细写入后失败"):
        service.publish_batch(
            batch["id"],
            service.get_batch(batch["id"])["revision"],
            "user-1",
            "核对事务",
        )
    with context.database.connect() as connection:
        _assert_projection(connection, base["version_id"])
        assert {
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT result_version_id FROM classification_unit_semantics"
            )
        } == {base["version_id"]}
    assert service.get_batch(batch["id"])["status"] == "draft"


def test_upgrade_backfills_once_and_backup_restores_old_schema(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    version = _publish(context)
    settings = _settings(tmp_path)
    settings.ensure_directories()
    with context.database.transaction() as connection:
        _remove_projection(connection)
    with pytest.raises(RuntimeError, match="缺少表"):
        context.database.initialize(production=True)
    backup = upgrade_database(settings, app_stopped=True)
    with context.database.connect() as connection:
        _assert_projection(connection, version["version_id"])
        assert (
            connection.execute(
                "SELECT checksum FROM app_migrations WHERE migration_id = ?",
                (SEMANTIC_MIGRATION,),
            ).fetchone()[0]
            == SEMANTIC_MIGRATION_CHECKSUM
        )
    # 第二次升级无需读取原始语义，语义表也不能重复插入。
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_units SET classification_json = 'invalid-json'"
        )
    context.database.upgrade_schema()
    with context.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_unit_semantics"
            ).fetchone()[0]
            == 1
        )
    restore_backup(settings, backup)
    with context.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'classification_unit_semantics'"
            ).fetchone()
            is None
        )
        assert (
            connection.execute(
                "SELECT 1 FROM app_migrations WHERE migration_id = ?",
                (SEMANTIC_MIGRATION,),
            ).fetchone()
            is None
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM classification_units").fetchone()[
                0
            ]
            == 1
        )


def test_invalid_historical_json_rolls_back_upgrade(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    _publish(context)
    with context.database.transaction() as connection:
        _remove_projection(connection)
        connection.execute(
            "UPDATE classification_units SET classification_json = 'invalid-json'"
        )
    with pytest.raises(sqlite3.OperationalError, match="malformed JSON"):
        context.database.upgrade_schema()
    with context.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'classification_unit_semantics'"
            ).fetchone()
            is None
        )
        assert (
            connection.execute(
                "SELECT 1 FROM app_migrations WHERE migration_id = ?",
                (SEMANTIC_MIGRATION,),
            ).fetchone()
            is None
        )


def test_semantic_migration_rejects_changed_checksum(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE app_migrations SET checksum = 'changed' WHERE migration_id = ?",
            (SEMANTIC_MIGRATION,),
        )
    with pytest.raises(RuntimeError, match="分类语义明细迁移校验失败"):
        context.database.upgrade_schema()


def test_removing_result_version_cascades_semantic_rows(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    version = _publish(context)
    with context.database.transaction() as connection:
        _assert_projection(connection, version["version_id"])
        connection.execute(
            "DELETE FROM classification_result_versions WHERE id = ?",
            (version["version_id"],),
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_unit_semantics"
            ).fetchone()[0]
            == 0
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchone() is None
