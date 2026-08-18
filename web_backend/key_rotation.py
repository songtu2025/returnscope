from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from web_backend.backup import create_backup
from web_backend.database import Database
from web_backend.security import SecretBox
from web_backend.settings import Settings


class KeyRotationError(ValueError):
    pass


@dataclass(frozen=True)
class KeyRotationResult:
    rotated_count: int
    backup_path: Path


def _keys_match(first: SecretBox, second: SecretBox) -> bool:
    probe = first.encrypt("key-rotation-probe")
    try:
        second.decrypt(probe)
    except ValueError:
        return False
    return True


def rotate_api_config_keys(
    settings: Settings,
    *,
    app_stopped: bool,
    new_key: str,
    old_key: str | None,
    from_development_key: bool,
) -> KeyRotationResult:
    if not app_stopped:
        raise KeyRotationError("轮换前必须停止应用，并传入 --app-stopped")

    clean_new_key = new_key.strip()
    clean_old_key = (old_key or "").strip()
    if not clean_new_key:
        raise KeyRotationError("缺少 WEBAPP_ENCRYPTION_KEY")
    if from_development_key and clean_old_key:
        raise KeyRotationError(
            "--from-development-key 与 WEBAPP_OLD_ENCRYPTION_KEY 不能同时使用"
        )
    if not from_development_key and not clean_old_key:
        raise KeyRotationError(
            "缺少 WEBAPP_OLD_ENCRYPTION_KEY；从开发密钥迁移时请传入 "
            "--from-development-key"
        )

    new_box = SecretBox(clean_new_key)
    old_box = SecretBox("" if from_development_key else clean_old_key)
    development_box = SecretBox("")
    if not from_development_key and _keys_match(old_box, development_box):
        raise KeyRotationError(
            "从开发默认密钥迁移必须传入 --from-development-key"
        )
    if _keys_match(old_box, new_box):
        raise KeyRotationError("新旧加密密钥不能相同")

    database = Database(settings.database_path)
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT id, api_key_ciphertext
            FROM api_config_versions
            WHERE api_key_ciphertext IS NOT NULL
              AND TRIM(api_key_ciphertext) <> ''
            ORDER BY id
            """
        ).fetchall()
    if not rows:
        raise KeyRotationError("没有可轮换的 API 密钥密文")

    prepared: list[tuple[str, str, str]] = []
    for row in rows:
        version_id = str(row["id"])
        old_ciphertext = str(row["api_key_ciphertext"])
        plaintext = old_box.decrypt(old_ciphertext)
        new_ciphertext = new_box.encrypt(plaintext)
        if new_box.decrypt(new_ciphertext) != plaintext:
            raise KeyRotationError("新密钥内存验证失败")
        prepared.append((version_id, old_ciphertext, new_ciphertext))

    backup_path = create_backup(settings)
    with database.transaction(immediate=True) as connection:
        for version_id, old_ciphertext, new_ciphertext in prepared:
            updated = connection.execute(
                """
                UPDATE api_config_versions
                SET api_key_ciphertext = ?
                WHERE id = ? AND api_key_ciphertext = ?
                """,
                (new_ciphertext, version_id, old_ciphertext),
            )
            if updated.rowcount != 1:
                raise KeyRotationError("配置在轮换期间发生变化，数据库未修改")

    return KeyRotationResult(
        rotated_count=len(prepared),
        backup_path=backup_path,
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="离线轮换 API 配置加密密钥")
    parser.add_argument(
        "--app-stopped",
        action="store_true",
        help="确认 Web 应用和后台任务已停止",
    )
    parser.add_argument(
        "--from-development-key",
        action="store_true",
        help="明确从内置开发密钥迁移",
    )
    args = parser.parse_args(argv)
    if not args.app_stopped:
        parser.error("轮换前必须停止应用，并传入 --app-stopped")
    try:
        settings = Settings.from_env()
        result = rotate_api_config_keys(
            settings,
            app_stopped=args.app_stopped,
            new_key=os.getenv("WEBAPP_ENCRYPTION_KEY", ""),
            old_key=os.getenv("WEBAPP_OLD_ENCRYPTION_KEY"),
            from_development_key=args.from_development_key,
        )
    except (KeyRotationError, ValueError) as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "rotated_count": result.rotated_count,
                "backup_path": str(result.backup_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
