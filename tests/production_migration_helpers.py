from __future__ import annotations

from pathlib import Path

from web_backend.database import Database
from web_backend.security import SecretBox
from web_backend.settings import Settings

OLD_RUNTIME_ROOT = "C:/accepted/runtime"


def build_migration_settings(data_dir: Path, encryption_key: str = "") -> Settings:
    return Settings(
        data_dir=data_dir,
        database_path=data_dir / "app.db",
        session_days=14,
        task_workers=15,
        bootstrap_email="admin@example.com",
        bootstrap_name="系统管理员",
        bootstrap_password="change-me-now",
        encryption_key=encryption_key,
        secure_cookies=False,
    )


def seed_migration_source(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "source"
    for directory_name in ("uploads", "imports", "results", "cache"):
        (source / directory_name).mkdir(parents=True)
    files = {
        "uploads/returns.csv": "return-data",
        "uploads/products.xlsx": "product-data",
        "imports/return-import.csv": "raw-return-data",
        "results/task.xlsx": "task-result",
        "results/task.json": "{}",
        "results/segment.xlsx": "segment-result",
        "results/segment.json": "{}",
        "cache/config-1.jsonl": "cache-entry\n",
    }
    for relative, content in files.items():
        (source / relative).write_text(content, encoding="utf-8")

    database = Database(source / "app.db")
    database.initialize()
    ciphertext = SecretBox("").encrypt("migration-secret")
    now = "2026-08-12T00:00:00+00:00"
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO users(id, email, display_name, password_hash, created_at)
            VALUES ('user-1', 'admin@example.com', '管理员', 'hash', ?)
            """,
            (now,),
        )
        connection.execute(
            """
            INSERT INTO sessions(id, user_id, token_hash, expires_at, created_at)
            VALUES ('session-1', 'user-1', 'token-hash', '2099-01-01', ?)
            """,
            (now,),
        )
        for dataset_id, kind in (
            ("returns-dataset", "returns"),
            ("products-dataset", "products"),
        ):
            connection.execute(
                """
                INSERT INTO datasets(
                    id, name, kind, current_version, created_by,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 1, 'user-1', ?, ?)
                """,
                (dataset_id, dataset_id, kind, now, now),
            )
        for version_id, dataset_id, file_name in (
            ("returns-version", "returns-dataset", "returns.csv"),
            ("products-version", "products-dataset", "products.xlsx"),
        ):
            connection.execute(
                """
                INSERT INTO dataset_versions(
                    id, dataset_id, version, file_path, original_name,
                    content_type, size_bytes, sha256, row_count, column_count,
                    schema_json, quality_json, created_by, created_at
                ) VALUES (?, ?, 1, ?, ?, 'application/octet-stream', 1,
                          'sha', 1, 1, '[]', '{}', 'user-1', ?)
                """,
                (
                    version_id,
                    dataset_id,
                    f"{OLD_RUNTIME_ROOT}/uploads/{file_name}",
                    file_name,
                    now,
                ),
            )
        connection.execute(
            """
            INSERT INTO dataset_imports(
                id, dataset_id, resulting_version_id, mode, raw_file_path,
                original_name, content_type, size_bytes, raw_sha256,
                row_count, column_count, schema_json, quality_json,
                imported_row_count, skipped_row_count, created_by, created_at
            ) VALUES ('import-1', 'returns-dataset', 'returns-version', 'create',
                      ?, 'return-import.csv', 'text/csv', 1, 'raw-sha',
                      1, 1, '[]', '{}', 1, 0, 'user-1', ?)
            """,
            (f"{OLD_RUNTIME_ROOT}/imports/return-import.csv", now),
        )
        connection.execute(
            """
            INSERT INTO api_connections(
                id, name, provider, created_by, created_at, updated_at
            ) VALUES ('connection-1', '模型连接', 'responses-compatible',
                      'user-1', ?, ?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO api_config_versions(
                id, connection_id, version, base_url, api_key_ciphertext,
                primary_model, primary_effort, created_by, created_at
            ) VALUES ('config-1', 'connection-1', 1, 'https://example.com', ?,
                      'gpt-test', 'medium', 'user-1', ?)
            """,
            (ciphertext, now),
        )
        connection.execute(
            """
            INSERT INTO tasks(
                id, title, owner_id, dataset_version_id, product_version_id,
                config_version_id, store, status, stage, snapshot_json,
                result_file_path, results_json_path, created_at
            ) VALUES ('task-1', '迁移任务', 'user-1', 'returns-version',
                      'products-version', 'config-1', 'SEEKWAY:US', 'completed',
                      '分析完成', '{}', ?, ?, ?)
            """,
            (
                f"{OLD_RUNTIME_ROOT}/results/task.xlsx",
                f"{OLD_RUNTIME_ROOT}/results/task.json",
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO task_segments(
                id, task_id, segment_key, agent_key, agent_family,
                taxonomy_version, status, result_file_path, result_json_path,
                created_at
            ) VALUES ('segment-1', 'task-1', 'L1', 'footwear', '鞋履智能体',
                      'taxonomy-v1', 'completed', ?, ?, ?)
            """,
            (
                f"{OLD_RUNTIME_ROOT}/results/segment.xlsx",
                f"{OLD_RUNTIME_ROOT}/results/segment.json",
                now,
            ),
        )
    return source, ciphertext
