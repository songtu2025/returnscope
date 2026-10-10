from pathlib import Path
from typing import Any

import pytest
from test_config_service import _database

from web_backend.common import add_audit, insert_audit, list_audit


@pytest.mark.parametrize("entrypoint", ("supplied_connection", "own_transaction"))
@pytest.mark.parametrize(
    "snapshots",
    (
        (None, False, None, "false"),
        (False, 0, "false", "0"),
        (0, None, "0", None),
    ),
)
def test_audit_preserves_null_false_zero_snapshots_and_timestamp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entrypoint: str,
    snapshots: tuple[Any, Any, str | None, str | None],
) -> None:
    before, after, before_json, after_json = snapshots
    database = _database(tmp_path)
    default_time = "2026-09-11T00:00:00+00:00"
    supplied_time = "2026-09-10T00:00:00+00:00"
    monkeypatch.setattr("web_backend.common.utc_now", lambda: default_time)
    if entrypoint == "supplied_connection":
        with database.transaction() as connection:
            insert_audit(
                connection,
                "task",
                "synthetic-task",
                "inspect",
                "user-1",
                before,
                after,
                supplied_time,
            )
        expected_time = supplied_time
    else:
        add_audit(
            database,
            "task",
            "synthetic-task",
            "inspect",
            "user-1",
            before=before,
            after=after,
        )
        expected_time = default_time
    with database.connect() as connection:
        row = connection.execute(
            "SELECT before_json, after_json, created_at FROM audit_logs"
        ).fetchone()
    assert row is not None
    assert tuple(row) == (before_json, after_json, expected_time)
    items = list_audit(database, "task", "synthetic-task")
    assert len(items) == 1
    item = items[0]
    assert item["before"] == before
    assert item["after"] == after
    assert type(item["before"]) is type(before)
    assert type(item["after"]) is type(after)
    assert item["created_at"] == expected_time
