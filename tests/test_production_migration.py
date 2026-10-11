from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from production_migration_helpers import OLD_RUNTIME_ROOT
from production_migration_helpers import build_migration_settings as _settings
from production_migration_helpers import seed_migration_source as _seed_source

from web_backend.key_rotation import rotate_api_config_keys
from web_backend.production_migration import (
    ProductionMigrationError,
    main,
    migrate_production_data,
)
from web_backend.security import SecretBox


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
    assert result.rebased_path_count == 7
    assert result.backup_path.is_file()
    assert (target / "cache/config-1.jsonl").read_text(encoding="utf-8") == (
        "cache-entry\n"
    )
    assert (target / "imports/return-import.csv").read_text(encoding="utf-8") == (
        "raw-return-data"
    )
    with zipfile.ZipFile(result.backup_path) as archive:
        assert "cache/config-1.jsonl" in archive.namelist()
        assert "imports/return-import.csv" in archive.namelist()
    with sqlite3.connect(target / "app.db") as connection:
        paths = [
            row[0]
            for row in connection.execute(
                "SELECT file_path FROM dataset_versions ORDER BY id"
            ).fetchall()
        ]
        raw_import_path = connection.execute(
            "SELECT raw_file_path FROM dataset_imports WHERE id = 'import-1'"
        ).fetchone()[0]
        target_ciphertext = connection.execute(
            "SELECT api_key_ciphertext FROM api_config_versions"
        ).fetchone()[0]
        session_count = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[
            0
        ]
    assert all(Path(path).is_relative_to(target) for path in paths)
    assert all(Path(path).is_file() for path in paths)
    assert Path(raw_import_path).is_relative_to(target)
    assert Path(raw_import_path).is_file()
    assert target_ciphertext == ciphertext
    assert session_count == 0
    with sqlite3.connect(source / "app.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT file_path FROM dataset_versions ORDER BY id LIMIT 1"
            )
            .fetchone()[0]
            .startswith(OLD_RUNTIME_ROOT)
        )


def test_migrates_legacy_source_without_imports_directory(tmp_path: Path) -> None:
    source, _ = _seed_source(tmp_path)
    with sqlite3.connect(source / "app.db") as connection:
        connection.execute("DELETE FROM dataset_imports")
        connection.commit()
    (source / "imports" / "return-import.csv").unlink()
    (source / "imports").rmdir()
    target = tmp_path / "production"

    result = migrate_production_data(
        source_root=source,
        target_root=target,
        backup_dir=tmp_path / "backups",
        app_stopped=True,
    )

    assert result.rebased_path_count == 6
    assert (target / "imports").is_dir()
    assert not list((target / "imports").iterdir())


def test_migration_clears_missing_checkpoint_for_zero_progress_segment(
    tmp_path: Path,
) -> None:
    source, _ = _seed_source(tmp_path)
    missing_checkpoint = f"{OLD_RUNTIME_ROOT}/results/missing-checkpoint.json"
    with sqlite3.connect(source / "app.db") as connection:
        connection.execute(
            """
            UPDATE task_segments
            SET status = 'cancelled', progress_current = 0,
                model_calls = 0, cache_hits = 0, model_failures = 0,
                result_version = 0, result_publish_status = NULL,
                result_json_path = ?
            WHERE id = 'segment-1'
            """,
            (missing_checkpoint,),
        )
        connection.commit()

    target = tmp_path / "production"
    result = migrate_production_data(
        source_root=source,
        target_root=target,
        backup_dir=tmp_path / "backups",
        app_stopped=True,
    )

    assert result.rebased_path_count == 6
    with sqlite3.connect(target / "app.db") as connection:
        checkpoint_path = connection.execute(
            "SELECT result_json_path FROM task_segments WHERE id = 'segment-1'"
        ).fetchone()[0]
    assert checkpoint_path is None


def test_migration_refuses_missing_checkpoint_with_partial_progress(
    tmp_path: Path,
) -> None:
    source, _ = _seed_source(tmp_path)
    missing_checkpoint = f"{OLD_RUNTIME_ROOT}/results/missing-checkpoint.json"
    with sqlite3.connect(source / "app.db") as connection:
        connection.execute(
            """
            UPDATE task_segments
            SET status = 'paused', progress_current = 1,
                result_version = 0, result_publish_status = NULL,
                result_json_path = ?
            WHERE id = 'segment-1'
            """,
            (missing_checkpoint,),
        )
        connection.commit()

    target = tmp_path / "production"
    with pytest.raises(ProductionMigrationError, match="备份缺少数据库引用文件"):
        migrate_production_data(
            source_root=source,
            target_root=target,
            backup_dir=tmp_path / "backups",
            app_stopped=True,
        )

    assert target.is_dir()
    assert not any(target.iterdir())


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
        assert (
            connection.execute(
                "SELECT api_key_ciphertext FROM api_config_versions"
            ).fetchone()[0]
            == source_ciphertext
        )


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
