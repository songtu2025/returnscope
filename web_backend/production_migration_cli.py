from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Sequence

if TYPE_CHECKING:
    from web_backend.production_migration import ProductionMigrationResult


def run_migration_cli(
    argv: Sequence[str] | None,
    migrate: Callable[..., ProductionMigrationResult],
    error_type: type[ValueError],
) -> None:
    """解析离线搬运命令，复用调用方的搬运入口及错误类型。"""
    parser = argparse.ArgumentParser(description="离线迁移生产运行数据")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--backup-dir", required=True, type=Path)
    parser.add_argument("--stored-source-root")
    parser.add_argument("--app-stopped", action="store_true")
    args = parser.parse_args(argv)
    if not args.app_stopped:
        parser.error("迁移前必须停止应用，并传入 --app-stopped")
    try:
        result = migrate(
            source_root=args.source,
            target_root=args.target,
            backup_dir=args.backup_dir,
            app_stopped=True,
            stored_source_root=args.stored_source_root,
        )
    except error_type as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "copied_file_count": result.copied_file_count,
                "rebased_path_count": result.rebased_path_count,
                "encrypted_config_count": result.encrypted_config_count,
                "backup_path": str(result.backup_path),
                "next_step": "rotate_target_key_before_start",
            },
            ensure_ascii=False,
        )
    )
