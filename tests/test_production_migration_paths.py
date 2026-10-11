from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from production_migration_helpers import OLD_RUNTIME_ROOT
from production_migration_helpers import seed_migration_source as _seed_source

from web_backend.production_migration import (
    ProductionMigrationError,
    migrate_production_data,
)


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
