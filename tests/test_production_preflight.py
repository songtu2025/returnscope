from pathlib import Path

from cryptography.fernet import Fernet

from scripts.check_web_production import (
    REQUIRED_FILES,
    read_env_file,
    validate_environment,
    validate_project,
)
from scripts.smoke_web_production import validate_base_url


def valid_environment() -> dict[str, str]:
    return {
        "APP_DOMAIN": "analysis.example.com",
        "WEBAPP_BOOTSTRAP_EMAIL": "admin@example.com",
        "WEBAPP_BOOTSTRAP_NAME": "系统管理员",
        "WEBAPP_BOOTSTRAP_PASSWORD": "strong-production-password",
        "WEBAPP_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
        "WEBAPP_SESSION_DAYS": "14",
        "WEBAPP_TASK_WORKERS": "15",
        "WEBAPP_BACKUP_RETENTION_DAYS": "14",
    }


def test_valid_production_environment_passes() -> None:
    assert validate_environment(valid_environment()) == []


def test_production_environment_rejects_unsafe_values() -> None:
    values = valid_environment()
    values.update(
        {
            "APP_DOMAIN": "http://localhost:8000",
            "WEBAPP_BOOTSTRAP_EMAIL": "invalid",
            "WEBAPP_BOOTSTRAP_PASSWORD": "short",
            "WEBAPP_ENCRYPTION_KEY": "invalid",
            "WEBAPP_TASK_WORKERS": "14",
        }
    )

    errors = validate_environment(values)

    assert len(errors) == 5
    assert any("APP_DOMAIN" in error for error in errors)
    assert any("WEBAPP_TASK_WORKERS" in error for error in errors)


def test_env_reader_preserves_fernet_padding(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.production"
    env_file.write_text(
        "WEBAPP_ENCRYPTION_KEY=abc=\nAPP_DOMAIN=analysis.example.com\n",
        encoding="utf-8",
    )

    values = read_env_file(env_file)

    assert values["WEBAPP_ENCRYPTION_KEY"] == "abc="


def test_project_validation_lists_only_missing_files(tmp_path: Path) -> None:
    for relative_path in REQUIRED_FILES[:-1]:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    assert validate_project(tmp_path) == [f"缺少部署文件：{REQUIRED_FILES[-1]}"]


def test_smoke_test_requires_https_by_default() -> None:
    assert validate_base_url("https://analysis.example.com/") == (
        "https://analysis.example.com"
    )

    try:
        validate_base_url("http://127.0.0.1:8000")
    except ValueError as exc:
        assert "HTTPS" in str(exc)
    else:
        raise AssertionError("HTTP 地址不应通过生产冒烟校验")

    assert (
        validate_base_url(
            "http://127.0.0.1:8000",
            allow_http=True,
        )
        == "http://127.0.0.1:8000"
    )
