from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from web_backend.common import list_audit
from web_backend.database import Database
from web_backend.task_service import TaskRevisionConflict, TaskService
from web_backend.worker import TaskWorker


class NoopRunner:
    def run(self, _task_id: str) -> None:
        return

    def run_segment(self, _task_id: str, _segment_id: str) -> None:
        return

    def finalize_task(self, _task_id: str) -> None:
        return


def test_worker_limits_each_user_to_three_running_segments(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO users(
                id, email, display_name, password_hash, created_at
            ) VALUES ('user-1', 'user@example.com', '用户', 'hash', '2026-01-01')
            """
        )
        connection.execute(
            """
            INSERT INTO users(
                id, email, display_name, password_hash, created_at
            ) VALUES (
                'user-2', 'user2@example.com', '用户二', 'hash', '2026-01-01'
            )
            """
        )
        for kind in ("returns", "products"):
            connection.execute(
                """
                INSERT INTO datasets(
                    id, name, kind, current_version, created_by,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 1, 'user-1', '2026-01-01', '2026-01-01')
                """,
                (f"dataset-{kind}", kind, kind),
            )
            connection.execute(
                """
                INSERT INTO dataset_versions(
                    id, dataset_id, version, file_path, original_name,
                    content_type, size_bytes, sha256, row_count,
                    column_count, schema_json, quality_json,
                    created_by, created_at
                ) VALUES (?, ?, 1, 'file', 'file', 'text/plain', 1,
                          'hash', 1, 1, '[]', '{}', 'user-1', '2026-01-01')
                """,
                (f"version-{kind}", f"dataset-{kind}"),
            )
        connection.execute(
            """
            INSERT INTO api_connections(
                id, name, provider, active_version_id,
                created_by, created_at, updated_at
            ) VALUES (
                'connection-1', '线路', 'responses-compatible', 'config-1',
                'user-1', '2026-01-01', '2026-01-01'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO api_config_versions(
                id, connection_id, version, base_url, api_key_ciphertext,
                primary_model, primary_effort, cheap_effort,
                secondary_effort, created_by, created_at, published_at
            ) VALUES (
                'config-1', 'connection-1', 1, 'https://example.com', 'key',
                'model', 'medium', 'low', 'high', 'user-1',
                '2026-01-01', '2026-01-01'
            )
            """
        )
        for index in range(4):
            connection.execute(
                """
                INSERT INTO tasks(
                    id, title, owner_id, dataset_version_id,
                    product_version_id, config_version_id,
                    store, status, stage, snapshot_json, created_at
                ) VALUES (?, ?, 'user-1', 'version-returns',
                          'version-products', 'config-1', 'STORE',
                          'queued', '等待运行', '{}', ?)
                """,
                (f"task-{index}", f"任务 {index}", f"2026-01-0{index + 1}"),
            )
            connection.execute(
                """
                INSERT INTO tasks(
                    id, title, owner_id, dataset_version_id,
                    product_version_id, config_version_id,
                    store, status, stage, snapshot_json, created_at
                ) VALUES (?, ?, 'user-2', 'version-returns',
                          'version-products', 'config-1', 'STORE',
                          'queued', '等待运行', '{}', ?)
                """,
                (
                    f"user-2-task-{index}",
                    f"用户二任务 {index}",
                    f"2026-02-0{index + 1}",
                ),
            )
            for owner_prefix in ("", "user-2-"):
                connection.execute(
                    """
                    INSERT INTO task_segments(
                        id, task_id, segment_key, agent_key, agent_family,
                        taxonomy_version, scope_json, status,
                        progress_total, execution_order, created_at
                    ) VALUES (?, ?, 'segment-1', 'footwear', '鞋履智能体',
                              'taxonomy-v1', '{}', 'queued', 1, 1, ?)
                    """,
                    (
                        f"{owner_prefix}segment-{index}",
                        f"{owner_prefix}task-{index}",
                        f"2026-03-0{index + 1}",
                    ),
                )

    worker = TaskWorker(database, NoopRunner(), concurrency=8)

    claimed = [worker._claim_next_segment() for _ in range(8)]

    owners = Counter(
        "user-2" if item and item[0].startswith("user-2-") else "user-1"
        for item in claimed
        if item is not None
    )
    assert owners == {"user-1": 3, "user-2": 3}
    assert claimed.count(None) == 2

    cancelled = TaskService(database).cancel(
        "task-3",
        "user-2",
        "业务范围调整，不再需要继续分析",
        expected_revision=1,
    )
    assert cancelled["status"] == "cancelled"
    event = TaskService(database).events("task-3")[-1]
    assert event["actor_name"] == "用户二"
    assert event["data"]["before"]["status"] == "queued"
    assert event["data"]["after"]["status"] == "cancelled"
    assert event["data"]["note"] == "业务范围调整，不再需要继续分析"
    audit = list_audit(database, "task", "task-3")[0]
    assert audit["actor_name"] == "用户二"
    assert audit["after"]["note"] == "业务范围调整，不再需要继续分析"
    with pytest.raises(TaskRevisionConflict):
        TaskService(database).cancel(
            "task-3",
            "user-1",
            "过期页面重复取消",
            expected_revision=1,
        )

    worker._recover_interrupted_tasks()
    with database.connect() as connection:
        running_count = connection.execute(
            "SELECT COUNT(*) AS count FROM task_segments WHERE status = 'running'"
        ).fetchone()["count"]
        queued_count = connection.execute(
            "SELECT COUNT(*) AS count FROM task_segments WHERE status = 'retry_pending'"
        ).fetchone()["count"]
    assert running_count == 0
    assert queued_count == 6
    recovered_event = TaskService(database).events("task-0")[-1]
    assert recovered_event["event_type"] == "recovered"
    assert recovered_event["message"] == "服务重启后 Listing 状态已恢复"
    worker.stop()
