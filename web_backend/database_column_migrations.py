from __future__ import annotations

import sqlite3


def migrate_user_columns(connection: sqlite3.Connection) -> None:
    user_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()
    }
    if "is_admin" not in user_columns:
        connection.execute(
            "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
        )


def migrate_dataset_columns(connection: sqlite3.Connection) -> None:
    dataset_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(datasets)").fetchall()
    }
    dataset_column_definitions = {
        "source_key": "TEXT",
        "usage_scope": "TEXT NOT NULL DEFAULT 'managed'",
    }
    for column_name, definition in dataset_column_definitions.items():
        if column_name not in dataset_columns:
            connection.execute(
                f"ALTER TABLE datasets ADD COLUMN {column_name} {definition}"
            )


def migrate_api_config_version_columns(
    connection: sqlite3.Connection,
) -> None:
    config_columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(api_config_versions)"
        ).fetchall()
    }
    if "change_note" not in config_columns:
        connection.execute(
            """
                ALTER TABLE api_config_versions
                ADD COLUMN change_note TEXT NOT NULL DEFAULT ''
                """
        )


def migrate_task_segment_columns(connection: sqlite3.Connection) -> None:
    segment_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(task_segments)").fetchall()
    }
    if "classification_keys_json" not in segment_columns:
        connection.execute(
            """
                ALTER TABLE task_segments
                ADD COLUMN classification_keys_json TEXT NOT NULL DEFAULT '[]'
                """
        )
    if "execution_order" not in segment_columns:
        connection.execute(
            """
                ALTER TABLE task_segments
                ADD COLUMN execution_order INTEGER NOT NULL DEFAULT 0
                """
        )
        rows = connection.execute(
            """
                SELECT id, task_id FROM task_segments
                ORDER BY task_id, created_at, segment_key
                """
        ).fetchall()
        task_positions: dict[str, int] = {}
        for row in rows:
            task_id = str(row["task_id"])
            position = task_positions.get(task_id, 0) + 1
            task_positions[task_id] = position
            connection.execute(
                "UPDATE task_segments SET execution_order = ? WHERE id = ?",
                (position, row["id"]),
            )
    for column_name in (
        "model_policy_version",
        "model_policy_json",
        "claims_version",
        "scope_json",
    ):
        if column_name not in segment_columns:
            connection.execute(
                f"ALTER TABLE task_segments ADD COLUMN {column_name} TEXT"
            )
    if "standard_version_id" not in segment_columns:
        connection.execute(
            "ALTER TABLE task_segments ADD COLUMN standard_version_id TEXT"
        )
    segment_column_definitions = {
        "requested_action": "TEXT",
        "revision": "INTEGER NOT NULL DEFAULT 1",
        "retry_count": "INTEGER NOT NULL DEFAULT 0",
        "model_failures": "INTEGER NOT NULL DEFAULT 0",
        "heartbeat_at": "TEXT",
        "result_file_path": "TEXT",
        "result_json_path": "TEXT",
        "result_version": "INTEGER NOT NULL DEFAULT 0",
        "result_version_id": "TEXT",
        "result_publish_status": "TEXT",
        "result_quality_status": "TEXT",
        "result_published_at": "TEXT",
        "result_publish_error": "TEXT",
    }
    for column_name, definition in segment_column_definitions.items():
        if column_name not in segment_columns:
            connection.execute(
                f"ALTER TABLE task_segments ADD COLUMN {column_name} {definition}"
            )


def migrate_result_version_columns(connection: sqlite3.Connection) -> None:
    version_columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(classification_result_versions)"
        ).fetchall()
    }
    version_column_definitions = {
        "parent_version_id": "TEXT REFERENCES classification_result_versions(id)",
        "version_reason": "TEXT NOT NULL DEFAULT ''",
        "created_by": "TEXT REFERENCES users(id)",
    }
    for column_name, definition in version_column_definitions.items():
        if column_name not in version_columns:
            connection.execute(
                "ALTER TABLE classification_result_versions "
                f"ADD COLUMN {column_name} {definition}"
            )


def migrate_classification_result_columns(
    connection: sqlite3.Connection,
) -> None:
    result_columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(classification_results)"
        ).fetchall()
    }
    if "standard_version_id" not in result_columns:
        connection.execute(
            "ALTER TABLE classification_results ADD COLUMN standard_version_id TEXT"
        )


def migrate_validation_run_columns(
    connection: sqlite3.Connection,
) -> None:
    validation_columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(classification_standard_validation_runs)"
        ).fetchall()
    }
    validation_column_definitions = {
        "approved_by": "TEXT REFERENCES users(id)",
        "approved_at": "TEXT",
        "approval_note": "TEXT NOT NULL DEFAULT ''",
    }
    for column_name, definition in validation_column_definitions.items():
        if column_name not in validation_columns:
            connection.execute(
                "ALTER TABLE classification_standard_validation_runs "
                f"ADD COLUMN {column_name} {definition}"
            )


def migrate_task_columns(connection: sqlite3.Connection) -> None:
    task_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
    }
    task_column_definitions = {
        "pause_requested": "INTEGER NOT NULL DEFAULT 0",
        "max_parallel_segments": "INTEGER NOT NULL DEFAULT 3",
        "last_scheduled_at": "TEXT",
        "archived_at": "TEXT",
        "archived_by": "TEXT REFERENCES users(id)",
    }
    for column_name, definition in task_column_definitions.items():
        if column_name not in task_columns:
            connection.execute(
                f"ALTER TABLE tasks ADD COLUMN {column_name} {definition}"
            )
    connection.execute(
        """
            CREATE INDEX IF NOT EXISTS idx_tasks_archive_created
            ON tasks(archived_at, created_at DESC)
            """
    )
