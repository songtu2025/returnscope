from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from web_backend.database import Database
from web_backend.key_rotation import (
    KeyRotationError,
    main,
    rotate_api_config_keys,
)
from web_backend.security import SecretBox
from web_backend.settings import Settings


def _key() -> str:
    return Fernet.generate_key().decode("ascii")


def _development_key() -> str:
    return base64.urlsafe_b64encode(
        hashlib.sha256(b"development-only-key").digest()
    ).decode("ascii")


def _settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "runtime"
    data_dir.mkdir(parents=True)
    return Settings(
        data_dir=data_dir,
        database_path=data_dir / "app.db",
        session_days=14,
        task_workers=15,
        bootstrap_email="admin@example.com",
        bootstrap_name="系统管理员",
        bootstrap_password="change-me-now",
        encryption_key="",
        secure_cookies=False,
    )


def _seed_configs(
    settings: Settings,
    encryption_key: str,
    plaintexts: tuple[str, ...] = ("secret-one", "secret-two"),
) -> Database:
    database = Database(settings.database_path)
    database.initialize()
    box = SecretBox(encryption_key)
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
            INSERT INTO api_connections(
                id, name, provider, created_by, created_at, updated_at
            ) VALUES ('connection-1', '上线模型', 'responses-compatible',
                      'user-1', ?, ?)
            """,
            (now, now),
        )
        for index, plaintext in enumerate(plaintexts, start=1):
            connection.execute(
                """
                INSERT INTO api_config_versions(
                    id, connection_id, version, base_url,
                    api_key_ciphertext, primary_model, primary_effort,
                    created_by, created_at
                ) VALUES (?, 'connection-1', ?, 'https://example.com', ?,
                          'gpt-test', 'medium', 'user-1', ?)
                """,
                (f"config-{index}", index, box.encrypt(plaintext), now),
            )
    return database


def _ciphertexts(database: Database) -> list[str]:
    with database.connect() as connection:
        return [
            str(row["api_key_ciphertext"])
            for row in connection.execute(
                """
                SELECT api_key_ciphertext FROM api_config_versions
                ORDER BY id
                """
            ).fetchall()
        ]


def _set_cli_environment(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    new_key: str,
) -> None:
    monkeypatch.setenv("WEBAPP_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("WEBAPP_DATABASE_PATH", str(settings.database_path))
    monkeypatch.setenv("WEBAPP_BACKUP_DIR", str(settings.data_dir / "backups"))
    monkeypatch.setenv("WEBAPP_ENCRYPTION_KEY", new_key)
    monkeypatch.setenv("WEBAPP_PRODUCTION", "false")
    monkeypatch.delenv("WEBAPP_OLD_ENCRYPTION_KEY", raising=False)


def test_cli_rotates_development_key_and_leaks_no_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = _settings(tmp_path)
    database = _seed_configs(settings, "")
    original_ciphertexts = _ciphertexts(database)
    new_key = _key()
    _set_cli_environment(monkeypatch, settings, new_key)

    main(["--app-stopped", "--from-development-key"])

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert set(output) == {"rotated_count", "backup_path"}
    assert output["rotated_count"] == 2
    assert Path(output["backup_path"]).is_file()
    assert captured.err == ""
    for forbidden in ("secret-one", "secret-two", *original_ciphertexts):
        assert forbidden not in captured.out
        assert forbidden not in captured.err
    assert [SecretBox(new_key).decrypt(value) for value in _ciphertexts(database)] == [
        "secret-one",
        "secret-two",
    ]


def test_rotates_explicit_old_key_and_creates_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    old_key = _key()
    new_key = _key()
    database = _seed_configs(settings, old_key)
    monkeypatch.setenv("WEBAPP_BACKUP_DIR", str(settings.data_dir / "backups"))

    result = rotate_api_config_keys(
        settings,
        app_stopped=True,
        new_key=new_key,
        old_key=old_key,
        from_development_key=False,
    )

    assert result.rotated_count == 2
    assert result.backup_path.is_file()
    assert [SecretBox(new_key).decrypt(value) for value in _ciphertexts(database)] == [
        "secret-one",
        "secret-two",
    ]


def test_wrong_old_key_and_repeated_run_leave_database_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    old_key = _key()
    new_key = _key()
    database = _seed_configs(settings, old_key)
    monkeypatch.setenv("WEBAPP_BACKUP_DIR", str(settings.data_dir / "backups"))
    before = _ciphertexts(database)

    with pytest.raises(ValueError, match="无法解密 API 密钥"):
        rotate_api_config_keys(
            settings,
            app_stopped=True,
            new_key=new_key,
            old_key=_key(),
            from_development_key=False,
        )
    assert _ciphertexts(database) == before
    assert not list((settings.data_dir / "backups").glob("*.zip"))

    rotate_api_config_keys(
        settings,
        app_stopped=True,
        new_key=new_key,
        old_key=old_key,
        from_development_key=False,
    )
    rotated = _ciphertexts(database)
    backup_count = len(list((settings.data_dir / "backups").glob("*.zip")))
    with pytest.raises(ValueError, match="无法解密 API 密钥"):
        rotate_api_config_keys(
            settings,
            app_stopped=True,
            new_key=new_key,
            old_key=old_key,
            from_development_key=False,
        )
    assert _ciphertexts(database) == rotated
    assert len(list((settings.data_dir / "backups").glob("*.zip"))) == backup_count


def test_requires_stopped_app_and_explicit_development_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    database = _seed_configs(settings, "")
    before = _ciphertexts(database)
    development_key = Fernet.generate_key().decode("ascii")
    _set_cli_environment(monkeypatch, settings, development_key)

    with pytest.raises(SystemExit) as cli_error:
        main([])
    assert cli_error.value.code == 2

    with pytest.raises(KeyRotationError, match="--app-stopped"):
        rotate_api_config_keys(
            settings,
            app_stopped=False,
            new_key=development_key,
            old_key=None,
            from_development_key=True,
        )
    with pytest.raises(KeyRotationError, match="WEBAPP_OLD_ENCRYPTION_KEY"):
        rotate_api_config_keys(
            settings,
            app_stopped=True,
            new_key=development_key,
            old_key=None,
            from_development_key=False,
        )
    assert _ciphertexts(database) == before


def test_rejects_conflicting_empty_and_same_key_parameters(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    old_key = _key()
    _seed_configs(settings, old_key)

    with pytest.raises(KeyRotationError, match="不能同时使用"):
        rotate_api_config_keys(
            settings,
            app_stopped=True,
            new_key=_key(),
            old_key=old_key,
            from_development_key=True,
        )
    with pytest.raises(KeyRotationError, match="WEBAPP_ENCRYPTION_KEY"):
        rotate_api_config_keys(
            settings,
            app_stopped=True,
            new_key="",
            old_key=old_key,
            from_development_key=False,
        )
    with pytest.raises(KeyRotationError, match="不能相同"):
        rotate_api_config_keys(
            settings,
            app_stopped=True,
            new_key=old_key,
            old_key=old_key,
            from_development_key=False,
        )

    development_settings = _settings(tmp_path / "development")
    _seed_configs(development_settings, "")
    with pytest.raises(KeyRotationError, match="--from-development-key"):
        rotate_api_config_keys(
            development_settings,
            app_stopped=True,
            new_key=_key(),
            old_key=_development_key(),
            from_development_key=False,
        )


def test_rejects_database_without_ciphertext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    database = _seed_configs(settings, _key(), plaintexts=())
    monkeypatch.setenv("WEBAPP_BACKUP_DIR", str(settings.data_dir / "backups"))

    with pytest.raises(KeyRotationError, match="没有可轮换"):
        rotate_api_config_keys(
            settings,
            app_stopped=True,
            new_key=_key(),
            old_key=_key(),
            from_development_key=False,
        )
    with database.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM api_config_versions").fetchone()[0]
            == 0
        )
    assert not list((settings.data_dir / "backups").glob("*.zip"))
