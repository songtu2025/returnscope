from __future__ import annotations

import sys
from pathlib import Path

import pytest
from database_migration_helpers import build_migration_settings as _settings

from web_backend.database import Database
from web_backend.settings import Settings
from web_backend.upgrade_database import (
    main as upgrade_database_main,
)


def test_production_startup_validates_schema_without_modifying_it(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    with database.connect() as connection:
        before = [
            tuple(row)
            for row in connection.execute(
                "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
            )
        ]
    database.initialize(production=True)
    database.initialize(production=True)
    with database.connect() as connection:
        after = [
            tuple(row)
            for row in connection.execute(
                "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
            )
        ]
    assert after == before


def test_product_display_sync_index_survives_upgrade_and_avoids_full_scan(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    with database.connect() as connection:
        connection.execute("DROP INDEX idx_result_records_product_display")
    database.upgrade_schema()
    with database.connect() as connection:
        plan = connection.execute(
            "EXPLAIN QUERY PLAN UPDATE classification_result_records "
            "SET product_name = ? WHERE store_site = ? AND matched_msku = ? "
            "AND result_version_id IN (SELECT v.id FROM classification_result_versions v "
            "JOIN classification_results r ON r.id = v.result_id "
            "JOIN dataset_versions p ON p.id = r.product_version_id WHERE p.dataset_id = ?)",
            ("验收商品", "验收店铺", "验收SKU", "验收资料"),
        ).fetchall()
    assert any("idx_result_records_product_display" in row["detail"] for row in plan)
    assert not any(
        "SCAN classification_result_records" in row["detail"] for row in plan
    )


def test_production_startup_rejects_missing_database_and_index(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "app.db")
    with pytest.raises(RuntimeError, match="生产数据库不存在"):
        database.initialize(production=True)
    assert not database.path.exists()

    database.initialize()
    with database.connect() as connection:
        connection.execute("DROP INDEX idx_task_segments_status_order")
    before = database.path.read_bytes()
    with pytest.raises(RuntimeError, match="缺少索引"):
        database.initialize(production=True)
    assert database.path.read_bytes() == before


@pytest.mark.parametrize(
    ("original", "changed"),
    [
        ("revision INTEGER NOT NULL", "revision TEXT NOT NULL"),
        ("id TEXT PRIMARY KEY", "id TEXT"),
    ],
)
def test_production_startup_rejects_changed_column_definition(
    tmp_path: Path, original: str, changed: str
) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    with database.connect() as connection:
        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'review_revisions'"
        ).fetchone()[0]
        assert original in schema
        connection.execute("DROP TABLE review_revisions")
        connection.execute(schema.replace(original, changed))

    before = database.path.read_bytes()
    with pytest.raises(RuntimeError, match="字段 .* 定义不一致"):
        database.validate_production_schema()
    assert database.path.read_bytes() == before


def test_production_accepts_historical_column_order_with_same_index_keys(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    with database.connect() as connection:
        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'api_validation_events'"
        ).fetchone()[0]
        index_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'idx_api_validation_events_run'"
        ).fetchone()[0]
        original = (
            "run_id TEXT NOT NULL REFERENCES api_validation_runs(id) ON DELETE CASCADE,\n"
            "    event_type TEXT NOT NULL,"
        )
        changed = (
            "event_type TEXT NOT NULL,\n"
            "    run_id TEXT NOT NULL REFERENCES api_validation_runs(id) ON DELETE CASCADE,"
        )
        assert original in schema
        connection.execute("DROP TABLE api_validation_events")
        connection.execute(schema.replace(original, changed))
        connection.execute(index_sql)

    database.validate_production_schema()


def test_upgrade_check_only_reads_database_without_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    database = Database(settings.database_path)
    database.initialize()
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setattr(sys, "argv", ["upgrade_database", "--check-only"])

    before = settings.database_path.read_bytes()
    upgrade_database_main()
    assert settings.database_path.read_bytes() == before
    assert not (tmp_path / "backups").exists()

    with database.connect() as connection:
        connection.execute("DROP INDEX idx_task_segments_status_order")
    with pytest.raises(RuntimeError, match="缺少索引"):
        upgrade_database_main()
    assert not (tmp_path / "backups").exists()


def test_upgrade_check_only_rejects_changed_index_definition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    database = Database(settings.database_path)
    database.initialize()
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setattr(sys, "argv", ["upgrade_database", "--check-only"])
    with database.connect() as connection:
        connection.execute("DROP INDEX idx_task_segments_status_order")
        connection.execute(
            "CREATE INDEX idx_task_segments_status_order ON task_segments(task_id)"
        )

    before = settings.database_path.read_bytes()
    with pytest.raises(RuntimeError, match="索引 .* 定义不一致"):
        upgrade_database_main()
    assert settings.database_path.read_bytes() == before
    assert not (tmp_path / "backups").exists()
