from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pandas as pd
import pytest
from test_task_planning import (
    _add_resolved_product_version,
    _database_with_inputs,
)

from web_backend.database import Database
from web_backend.task_service import TaskService


@pytest.fixture
def insertion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    database, returns_path, products_path = _database_with_inputs(tmp_path)
    rows = pd.read_csv(returns_path, dtype=str).to_dict("records")
    rows.extend(
        [
            {**rows[0], "order-id": "ORDER-3"},
            {
                **rows[0],
                "order-id": "ORDER-4",
                "customer-comments": "鞋子偏小",
            },
        ]
    )
    pd.DataFrame(rows).to_csv(returns_path, index=False, encoding="utf-8-sig")
    product_version_id = _add_resolved_product_version(database, products_path)
    service = TaskService(database)
    prepared = service.plan_service.prepare(
        dataset_version_id="version-returns",
        product_version_id=product_version_id,
        store="SEEKWAY:US",
        listing="L1",
        config_version_id="config-1",
    )
    monkeypatch.setattr(service.plan_service, "prepare", Mock(return_value=prepared))
    return SimpleNamespace(
        database=database,
        service=service,
        prepared=prepared,
        product_version_id=product_version_id,
    )


def _create(insertion: SimpleNamespace, policy: str = "run_ready") -> dict[str, Any]:
    return insertion.service.create(
        actor_id="user-1",
        title="片段入库回归",
        dataset_version_id="version-returns",
        product_version_id=insertion.product_version_id,
        store="SEEKWAY:US",
        listing="L1",
        config_version_id="config-1",
        plan_hash=insertion.prepared.response["plan_hash"],
        unresolved_policy=policy,
        segment_order=[
            segment["segment_key"]
            for segment in reversed(insertion.prepared.response["segments"])
        ],
    )


def _rows(database: Database, table: str) -> list[dict[str, Any]]:
    with database.connect() as connection:
        return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]


def _snapshot(database: Database) -> dict[str, list[dict[str, Any]]]:
    return {
        table: _rows(database, table)
        for table in ("tasks", "task_segments", "task_events", "audit_logs")
    }


def _replan(insertion: SimpleNamespace, task: dict[str, Any]) -> dict[str, Any]:
    return insertion.service.replan(
        task_id=task["id"],
        actor_id="user-1",
        product_version_id=insertion.product_version_id,
        expected_revision=task["revision"],
        plan_hash=insertion.prepared.response["plan_hash"],
        unresolved_policy="run_ready",
        reason="验证剩余片段入库",
    )


def test_creation_persists_segment_metadata_and_keeps_plan(
    insertion: SimpleNamespace,
) -> None:
    prepared = insertion.prepared
    original = deepcopy(prepared.response)
    task = _create(insertion)
    planned = {segment["segment_key"]: segment for segment in original["segments"]}
    keys = prepared.execution_plan.classification_keys_by_segment(prepared.dataset)
    rows = sorted(
        _rows(insertion.database, "task_segments"),
        key=lambda row: row["execution_order"],
    )

    assert [row["segment_key"] for row in rows] == list(reversed(planned))
    for order, row in enumerate(rows, start=1):
        segment = planned[row["segment_key"]]
        assert row["task_id"] == task["id"]
        for field in (
            "agent_key",
            "agent_family",
            "logic_version",
            "taxonomy_version",
            "model_policy_version",
            "standard_version_id",
            "claims_version",
            "record_count",
            "unique_comments",
        ):
            assert row[field] == segment.get(field)
        assert row["status"] == "queued"
        assert row["progress_total"] == segment["unique_comments"]
        assert row["execution_order"] == order
        assert row["created_at"] == task["created_at"]
        assert json.loads(row["scope_json"]) == segment["scope"]
        assert json.loads(row["model_policy_json"]) == segment["model_policy"]
        assert json.loads(row["variants_json"]) == segment["variants"]
        assert json.loads(row["classification_keys_json"]) == keys[row["segment_key"]]
    assert prepared.response == original


@pytest.mark.parametrize("policy", ["block_all", "run_ready"])
@pytest.mark.parametrize("has_blocked", [False, True])
def test_creation_preserves_blocking_policy(
    insertion: SimpleNamespace, policy: str, has_blocked: bool
) -> None:
    prepared = insertion.prepared
    prepared.response["blocked_count"] = int(has_blocked)
    if has_blocked:
        prepared.response["segments"][0]["status"] = "blocked"
    original = deepcopy(prepared.response)

    _create(insertion, policy)

    planned = {segment["segment_key"]: segment for segment in original["segments"]}
    for row in _rows(insertion.database, "task_segments"):
        expected = (
            "blocked"
            if planned[row["segment_key"]]["status"] == "blocked"
            else "not_started"
            if has_blocked and policy == "block_all"
            else "queued"
        )
        assert row["status"] == expected
    assert prepared.response == original


@pytest.mark.parametrize("preserved_scope", ["all", "most_records", "fewest_records"])
def test_replan_preserves_completed_row_and_inserts_only_remaining_scope(
    insertion: SimpleNamespace, preserved_scope: str
) -> None:
    task = _create(insertion)
    prepared = insertion.prepared
    original = deepcopy(prepared.response)
    shoe = next(
        row
        for row in _rows(insertion.database, "task_segments")
        if row["agent_key"] == "footwear"
    )
    keys = json.loads(shoe["classification_keys_json"])
    counts = prepared.dataset.records["classification_key"].value_counts()
    preserve_all = preserved_scope == "all"
    select_key = min if preserved_scope == "fewest_records" else max
    preserved_keys = (
        keys if preserve_all else [select_key(keys, key=counts.__getitem__)]
    )
    with insertion.database.transaction(immediate=True) as connection:
        connection.execute(
            "UPDATE task_segments SET status = 'completed', classification_keys_json = ?, "
            "record_count = ?, unique_comments = ?, progress_total = ?, "
            "result_file_path = 'synthetic-completed.xlsx', result_version = 3, "
            "model_calls = 5, cache_hits = 7 WHERE id = ?",
            (
                json.dumps(preserved_keys),
                sum(int(counts[key]) for key in preserved_keys),
                len(preserved_keys),
                len(preserved_keys),
                shoe["id"],
            ),
        )
        connection.execute(
            "UPDATE tasks SET status = 'partial' WHERE id = ?", (task["id"],)
        )
    preserved = next(
        row
        for row in _rows(insertion.database, "task_segments")
        if row["id"] == shoe["id"]
    )

    replanned = _replan(insertion, task)

    rows = _rows(insertion.database, "task_segments")
    assert next(row for row in rows if row["id"] == shoe["id"]) == preserved
    remaining = [row for row in rows if row["id"] != shoe["id"]]
    assert len(remaining) == (1 if preserve_all else 2)
    assert sorted(row["execution_order"] for row in remaining) == list(
        range(shoe["execution_order"] + 1, shoe["execution_order"] + 1 + len(remaining))
    )
    for row in remaining:
        assert row["status"] == "queued"
        remaining_keys = json.loads(row["classification_keys_json"])
        expected_records = sum(int(counts[key]) for key in remaining_keys)
        assert row["record_count"] == expected_records
        assert row["unique_comments"] == row["progress_total"] == 1
        if preserved_scope != "fewest_records":
            assert expected_records == 1
        elif row["agent_key"] == "footwear":
            assert expected_records > 1
        assert row["created_at"] == replanned["heartbeat_at"]
        assert row["result_file_path"] is None
        assert row["model_calls"] == row["cache_hits"] == 0
        assert json.loads(row["variants_json"])[0]["record_count"] == expected_records
        assert json.loads(row["variants_json"])[0]["unique_comments"] == 1
        assert not set(json.loads(row["classification_keys_json"])) & set(
            preserved_keys
        )
        if row["agent_key"] == "footwear":
            assert (
                row["segment_key"]
                == f"{shoe['segment_key']}:{original['plan_hash'][:12]}"
            )
    assert prepared.response == original


@pytest.mark.parametrize("failure_at", [1, 2])
@pytest.mark.parametrize("replan", [False, True], ids=["creation", "replan"])
def test_insertion_failure_rolls_back_all_rows(
    insertion: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    failure_at: int,
    replan: bool,
) -> None:
    if replan:
        task = _create(insertion)
        with insertion.database.transaction(immediate=True) as connection:
            connection.execute(
                "UPDATE tasks SET status = 'blocked' WHERE id = ?", (task["id"],)
            )
    before = _snapshot(insertion.database)
    original = deepcopy(insertion.prepared.response)
    insert = insertion.service._insert_segment
    count = 0

    def fail_after_insert(*args: Any, **kwargs: Any) -> None:
        nonlocal count
        insert(*args, **kwargs)
        count += 1
        if count == failure_at:
            raise RuntimeError("模拟片段入库失败")

    monkeypatch.setattr(insertion.service, "_insert_segment", fail_after_insert)

    with pytest.raises(RuntimeError, match="模拟片段入库失败"):
        if replan:
            _replan(insertion, task)
        else:
            _create(insertion)

    assert count == failure_at
    assert _snapshot(insertion.database) == before
    assert insertion.prepared.response == original
