"""复用现有合成业务链，构造待清理与保留数据。"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_insight_reports import _complete_report
from test_review_dashboard_report_lifecycle import (
    _advance_dashboard,
    _publish_correction,
)
from test_review_dashboard_report_lifecycle import lifecycle as lifecycle
from test_web_backup import _settings

from web_backend.common import insert_audit


def _copy_row(connection, table, row, changes):
    values = {**dict(row), **changes}
    connection.execute(
        f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",
        tuple(values.values()),
    )


@pytest.fixture
def cleanup_context(lifecycle, tmp_path):
    derived = _publish_correction(lifecycle)
    dashboard = _advance_dashboard(lifecycle, derived)
    report = _complete_report(dashboard, lifecycle.reports)
    folder = tmp_path / "results" / "task-1"
    folder.mkdir(parents=True)
    result = folder / "analysis.xlsx"
    result.write_bytes(b"synthetic-result")
    (folder / "old-result.xlsx").write_bytes(b"synthetic-old-result")
    cache = tmp_path / "cache" / "task-1-config-1.jsonl"
    cache.parent.mkdir()
    cache.write_text("{}", encoding="utf-8")
    (cache.parent / "classification-standard-validation.jsonl").write_text("{}")
    with lifecycle.database.transaction(immediate=True) as connection:
        connection.execute("UPDATE users SET is_admin = 1 WHERE id = 'user-1'")
        connection.execute(
            "UPDATE tasks SET status = 'completed', result_file_path = ? WHERE id = 'task-1'",
            (str(result),),
        )
        connection.execute(
            "UPDATE task_segments SET result_json_path = ? WHERE task_id = 'task-1'",
            (str(result),),
        )
        for table, source_id, changes in (
            (
                "dataset_versions",
                "version-returns",
                {"id": "version-mysql", "version": 2},
            ),
            (
                "tasks",
                "task-1",
                {
                    "id": "task-keep",
                    "dataset_version_id": "version-mysql",
                    "result_file_path": None,
                },
            ),
            (
                "task_segments",
                "segment-1",
                {
                    "id": "segment-keep",
                    "task_id": "task-keep",
                    "result_json_path": None,
                    "result_version_id": None,
                },
            ),
            (
                "classification_results",
                lifecycle.base["result_id"],
                {
                    "id": "result-keep",
                    "source_task_id": "task-keep",
                    "source_segment_id": "segment-keep",
                    "dataset_version_id": "version-mysql",
                },
            ),
            (
                "classification_result_versions",
                lifecycle.base["version_id"],
                {
                    "id": "version-keep",
                    "result_id": "result-keep",
                    "source_segment_id": "segment-keep",
                },
            ),
        ):
            row = connection.execute(
                f"SELECT * FROM {table} WHERE id = ?", (source_id,)
            ).fetchone()
            _copy_row(connection, table, row, changes)
        insert_audit(
            connection,
            "dataset",
            "dataset-returns",
            "import_mysql_returns",
            "user-1",
            after={"version_id": "version-mysql"},
        )
    uploads = tmp_path / "uploads"
    uploads.mkdir(exist_ok=True)
    with lifecycle.database.transaction() as connection:
        for kind in ("returns", "products"):
            source = tmp_path / (
                "returns.csv" if kind == "returns" else "products.xlsx"
            )
            target = uploads / source.name
            source.rename(target)
            connection.execute(
                "UPDATE dataset_versions SET file_path = ? WHERE dataset_id = ?",
                (str(target), f"dataset-{kind}"),
            )
    settings = replace(
        _settings(tmp_path), data_dir=tmp_path, database_path=lifecycle.database.path
    )
    return SimpleNamespace(
        database=lifecycle.database,
        root=tmp_path,
        settings=settings,
        dashboard=dashboard,
        report=report,
    )
