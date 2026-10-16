import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from web_backend.datasets.return_store import (
    migrate_return_store,
    return_preview,
    save_return_frame,
)


@pytest.fixture
def connection():
    with sqlite3.connect(":memory:") as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(
            "CREATE TABLE dataset_versions(id TEXT PRIMARY KEY);"
            "CREATE TABLE app_migrations(migration_id TEXT PRIMARY KEY,checksum TEXT,status TEXT,applied_at TEXT);"
            "INSERT INTO dataset_versions VALUES ('version');"
        )
        migrate_return_store(connection)
        yield connection


def test_store_preserves_values_and_filters_like_dataframe(connection):
    frame = pd.DataFrame(
        [
            {
                "sku": "001",
                "店铺/站点": " A ",
                "备注": "ÄBC 100%",
                "品类A": "鞋",
                "品类B": "水鞋",
            },
            {
                "sku": "002",
                "店铺/站点": "B",
                "备注": "a_b",
                "品类A": "手套",
                "品类B": "",
            },
            {"sku": "003", "店铺/站点": "B", "备注": "", "品类A": "", "品类B": "儿童"},
        ]
    )
    save_return_frame(connection, "version", frame)
    version = {"id": "version", "selected_version": 3}

    def preview(**filters):
        return return_preview(
            connection,
            version,
            (0, 50),
            {"query": "", "store": "", "category": "", **filters},
        )

    assert preview(query="äbc")["records"][0]["sku"] == "001"
    assert preview(query="%")["total"] == 1
    assert preview(query="_")["total"] == 1
    assert preview(query="sku")["total"] == 0
    assert preview(query="001\0 A")["total"] == 0
    assert preview(store="A", category="鞋 > 水鞋")["total"] == 1
    assert preview(category="儿童")["records"][0]["sku"] == "003"
    assert preview(store="B")["total"] == 2
    assert preview()["version"] == 3
    assert preview()["records"] == [
        {**record, "_row_index": index}
        for index, record in enumerate(frame.to_dict("records"))
    ]
    assert preview()["facets"]["categories"] == []
    assert preview(query="001")["facets"]["categories"] == ["儿童", "手套", "鞋 > 水鞋"]


def test_duplicate_write_is_immutable_and_version_delete_cascades(connection):
    frame = pd.DataFrame({"sku": ["001"]})
    save_return_frame(connection, "version", frame)
    save_return_frame(connection, "version", pd.DataFrame({"sku": ["002"]}))
    assert json.loads(
        connection.execute("SELECT values_json FROM return_rows").fetchone()[0]
    ) == ["001"]
    connection.execute("DELETE FROM dataset_versions")
    assert connection.execute("SELECT count(*) FROM return_rows").fetchone()[0] == 0
    assert connection.execute("SELECT count(*) FROM return_rowsets").fetchone()[0] == 0


def test_empty_snapshot_and_missing_store_column(connection):
    save_return_frame(connection, "version", pd.DataFrame(columns=["sku"]))
    preview = return_preview(
        connection,
        {"id": "version", "selected_version": 1},
        (100, 10),
        {"store": "ignored", "category": "", "query": ""},
    )
    assert preview["total"] == 0 and preview["records"] == []


def test_return_backfill_is_verified_and_rollback_is_atomic(tmp_path):
    from types import SimpleNamespace

    from return_import_helpers import _create_task_input, _return_row, _write_returns
    from test_classification_result_pool import _seed_result_context

    from web_backend.dataset_files import _sha256_file
    from web_backend.dataset_service import DatasetService
    from web_backend.datasets.return_backfill import backfill_return_store

    seed = _seed_result_context(tmp_path)
    service = DatasetService(seed.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "feedback.csv"
    _write_returns(source, [_return_row("001", "合成数据")])
    created = _create_task_input(service, source)
    with seed.database.transaction() as c:
        c.execute("DELETE FROM return_rowsets")
        rows = c.execute(
            "SELECT v.id,v.file_path FROM dataset_versions v JOIN datasets d ON d.id=v.dataset_id WHERE d.kind='returns'"
        ).fetchall()
        for row in rows:
            c.execute(
                "UPDATE dataset_versions SET sha256=? WHERE id=?",
                (_sha256_file(Path(row["file_path"])), row["id"]),
            )
    outcome = backfill_return_store(seed.database)
    assert outcome["versions"] == 2
    assert service.preview_rows(created["id"])["records"][0]["order-id"] == "001"
    with seed.database.transaction() as c:
        c.execute("DELETE FROM return_rowsets")
    Path(service.version_file(created["id"])["file_path"]).write_bytes(b"broken")
    with pytest.raises(ValueError, match="摘要不一致"):
        backfill_return_store(seed.database)
    with seed.database.connect() as c:
        assert c.execute("SELECT count(*) FROM return_rows").fetchone()[0] == 0
