from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from web_backend.database import Database
from web_backend.key_rotation import rotate_api_config_keys
from web_backend.production_migration import (
    ProductionMigrationError,
    main,
    migrate_production_data,
)
from web_backend.security import SecretBox
from web_backend.settings import Settings

OLD_RUNTIME_ROOT = "C:/accepted/runtime"


def _settings(data_dir: Path, encryption_key: str = "") -> Settings:
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


def _seed_source(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "source"
    for directory_name in ("uploads", "results", "cache"):
        (source / directory_name).mkdir(parents=True)
    files = {
        "uploads/returns.csv": "return-data",
        "uploads/products.xlsx": "product-data",
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


def test_migrates_to_empty_target_rebases_paths_and_preserves_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, ciphertext = _seed_source(tmp_path)
    target = tmp_path / "production"
    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("WEBAPP_BACKUP_DIR", str(backup_dir))

    result = migrate_production_data(
        source_root=source,
        target_root=target,
        backup_dir=backup_dir,
        app_stopped=True,
    )

    assert result.encrypted_config_count == 1
    assert result.rebased_path_count == 6
    assert result.backup_path.is_file()
    assert (target / "cache/config-1.jsonl").read_text(encoding="utf-8") == (
        "cache-entry\n"
    )
    with zipfile.ZipFile(result.backup_path) as archive:
        assert "cache/config-1.jsonl" in archive.namelist()
    with sqlite3.connect(target / "app.db") as connection:
        paths = [
            row[0]
            for row in connection.execute(
                "SELECT file_path FROM dataset_versions ORDER BY id"
            ).fetchall()
        ]
        target_ciphertext = connection.execute(
            "SELECT api_key_ciphertext FROM api_config_versions"
        ).fetchone()[0]
        session_count = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert all(Path(path).is_relative_to(target) for path in paths)
    assert all(Path(path).is_file() for path in paths)
    assert target_ciphertext == ciphertext
    assert session_count == 0
    with sqlite3.connect(source / "app.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        assert connection.execute(
            "SELECT file_path FROM dataset_versions ORDER BY id LIMIT 1"
        ).fetchone()[0].startswith(OLD_RUNTIME_ROOT)


def test_key_rotation_runs_on_imported_target_before_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, source_ciphertext = _seed_source(tmp_path)
    target = tmp_path / "production"
    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("WEBAPP_BACKUP_DIR", str(backup_dir))
    migrate_production_data(
        source_root=source,
        target_root=target,
        backup_dir=backup_dir,
        app_stopped=True,
    )
    new_key = Fernet.generate_key().decode("ascii")

    rotation = rotate_api_config_keys(
        _settings(target, new_key),
        app_stopped=True,
        new_key=new_key,
        old_key=None,
        from_development_key=True,
    )

    assert rotation.rotated_count == 1
    with sqlite3.connect(target / "app.db") as connection:
        target_ciphertext = connection.execute(
            "SELECT api_key_ciphertext FROM api_config_versions"
        ).fetchone()[0]
    assert SecretBox(new_key).decrypt(target_ciphertext) == "migration-secret"
    with sqlite3.connect(source / "app.db") as connection:
        assert connection.execute(
            "SELECT api_key_ciphertext FROM api_config_versions"
        ).fetchone()[0] == source_ciphertext


def test_refuses_nonempty_target_before_backup(tmp_path: Path) -> None:
    source, _ = _seed_source(tmp_path)
    target = tmp_path / "production"
    target.mkdir()
    (target / "existing.txt").write_text("keep", encoding="utf-8")
    backup_dir = tmp_path / "backups"

    with pytest.raises(ProductionMigrationError, match="非空"):
        migrate_production_data(
            source_root=source,
            target_root=target,
            backup_dir=backup_dir,
            app_stopped=True,
        )

    assert (target / "existing.txt").read_text(encoding="utf-8") == "keep"
    assert not backup_dir.exists()


def test_refuses_source_target_containment_in_both_directions(tmp_path: Path) -> None:
    source, _ = _seed_source(tmp_path / "target-parent")
    containing_target = source.parent
    with pytest.raises(ProductionMigrationError, match="互相包含"):
        migrate_production_data(
            source_root=source,
            target_root=containing_target,
            backup_dir=tmp_path / "backups-parent-case",
            app_stopped=True,
        )

    child_target = source / "production"
    child_target.mkdir()
    with pytest.raises(ProductionMigrationError, match="互相包含"):
        migrate_production_data(
            source_root=source,
            target_root=child_target,
            backup_dir=tmp_path / "backups-child-case",
            app_stopped=True,
        )
    assert not any(child_target.iterdir())


def test_refuses_backup_containment_in_both_directions(tmp_path: Path) -> None:
    source, _ = _seed_source(tmp_path / "source-parent")
    target = tmp_path / "production"
    overlapping_backups = (
        source / "backups",
        source.parent,
        target / "backups",
        target.parent / "production-parent",
    )
    nested_target = overlapping_backups[-1] / "app-data"
    for backup_dir, migration_target in (
        (overlapping_backups[0], target),
        (overlapping_backups[1], target),
        (overlapping_backups[2], target),
        (overlapping_backups[3], nested_target),
    ):
        with pytest.raises(ProductionMigrationError, match="备份目录必须独立"):
            migrate_production_data(
                source_root=source,
                target_root=migration_target,
                backup_dir=backup_dir,
                app_stopped=True,
            )


def test_requires_stopped_app_and_valid_source(tmp_path: Path) -> None:
    source, _ = _seed_source(tmp_path)
    with pytest.raises(ProductionMigrationError, match="--app-stopped"):
        migrate_production_data(
            source_root=source,
            target_root=tmp_path / "target",
            backup_dir=tmp_path / "backups",
            app_stopped=False,
        )
    with pytest.raises(ProductionMigrationError, match="源运行目录"):
        migrate_production_data(
            source_root=tmp_path / "missing",
            target_root=tmp_path / "target",
            backup_dir=tmp_path / "backups",
            app_stopped=True,
        )


def test_path_validation_failure_keeps_target_empty(tmp_path: Path) -> None:
    source, _ = _seed_source(tmp_path)
    with sqlite3.connect(source / "app.db") as connection:
        connection.execute(
            "UPDATE dataset_versions SET file_path = '/outside/returns.csv' "
            "WHERE id = 'returns-version'"
        )
        connection.commit()
    target = tmp_path / "target"

    with pytest.raises(ProductionMigrationError, match="旧运行目录"):
        migrate_production_data(
            source_root=source,
            target_root=target,
            backup_dir=tmp_path / "backups",
            app_stopped=True,
            stored_source_root=OLD_RUNTIME_ROOT,
        )

    assert target.is_dir()
    assert not any(target.iterdir())


def test_cli_output_contains_counts_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source, ciphertext = _seed_source(tmp_path)
    target = tmp_path / "target"
    backup_dir = tmp_path / "backups"

    main(
        [
            "--source",
            str(source),
            "--target",
            str(target),
            "--backup-dir",
            str(backup_dir),
            "--app-stopped",
        ]
    )

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert set(output) == {
        "copied_file_count",
        "rebased_path_count",
        "encrypted_config_count",
        "backup_path",
        "next_step",
    }
    assert "migration-secret" not in captured.out
    assert ciphertext not in captured.out
