from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from return_semantics.model_client import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIRECTORIES = ("uploads", "imports", "results", "cache")


def _read_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数") from exc
    if value < minimum:
        raise ValueError(f"{name} 不能小于 {minimum}")
    return value


def _read_bool(name: str, default: bool = False) -> bool:
    fallback = "true" if default else "false"
    return os.getenv(name, fallback).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_path: Path
    session_days: int
    task_workers: int
    bootstrap_email: str
    bootstrap_name: str
    bootstrap_password: str
    encryption_key: str
    secure_cookies: bool
    production: bool = False
    public_web_url: str = "http://127.0.0.1:5173"
    mail_provider: str = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = field(default="", repr=False)
    smtp_from: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    invitation_ttl_hours: int = 24
    password_reset_ttl_minutes: int = 30
    password_min_length: int = 12
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = ""
    mysql_password: str = field(default="", repr=False)
    mysql_database: str = "jijia_sync_isolated_20260827"
    mysql_table: str = "sale_return_order"
    mysql_max_rows: int = 100000

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(PROJECT_ROOT / ".env.mysql")
        data_dir = Path(
            os.getenv("WEBAPP_DATA_DIR", PROJECT_ROOT / "runtime")
        ).resolve()
        database_path = Path(
            os.getenv("WEBAPP_DATABASE_PATH", data_dir / "app.db")
        ).resolve()
        settings = cls(
            mysql_host=os.getenv("WEBAPP_MYSQL_HOST", "127.0.0.1").strip(),
            mysql_port=_read_int("WEBAPP_MYSQL_PORT", 3306),
            mysql_user=os.getenv("WEBAPP_MYSQL_USER", "").strip(),
            mysql_password=os.getenv("WEBAPP_MYSQL_PASSWORD", ""),
            mysql_database=os.getenv(
                "WEBAPP_MYSQL_DATABASE", "jijia_sync_isolated_20260827"
            ).strip(),
            mysql_table=os.getenv("WEBAPP_MYSQL_TABLE", "sale_return_order").strip(),
            mysql_max_rows=_read_int("WEBAPP_MYSQL_MAX_ROWS", 100000),
            data_dir=data_dir,
            database_path=database_path,
            session_days=_read_int("WEBAPP_SESSION_DAYS", 14),
            task_workers=_read_int("WEBAPP_TASK_WORKERS", 15),
            bootstrap_email=os.getenv(
                "WEBAPP_BOOTSTRAP_EMAIL",
                "admin@example.com",
            )
            .strip()
            .lower(),
            bootstrap_name=os.getenv(
                "WEBAPP_BOOTSTRAP_NAME",
                "系统管理员",
            ).strip(),
            bootstrap_password=os.getenv(
                "WEBAPP_BOOTSTRAP_PASSWORD",
                "change-me-now",
            ),
            encryption_key=os.getenv("WEBAPP_ENCRYPTION_KEY", "").strip(),
            secure_cookies=_read_bool("WEBAPP_SECURE_COOKIES"),
            production=_read_bool("WEBAPP_PRODUCTION"),
            public_web_url=os.getenv(
                "WEBAPP_PUBLIC_URL", "http://127.0.0.1:5173"
            ).strip(),
            mail_provider=os.getenv("WEBAPP_MAIL_PROVIDER", "console").strip().lower(),
            smtp_host=os.getenv("WEBAPP_SMTP_HOST", "").strip(),
            smtp_port=_read_int("WEBAPP_SMTP_PORT", 587),
            smtp_user=os.getenv("WEBAPP_SMTP_USER", "").strip(),
            smtp_password=os.getenv("WEBAPP_SMTP_PASSWORD", ""),
            smtp_from=os.getenv("WEBAPP_SMTP_FROM", "").strip(),
            smtp_use_tls=_read_bool("WEBAPP_SMTP_USE_TLS", True),
            smtp_use_ssl=_read_bool("WEBAPP_SMTP_USE_SSL"),
            invitation_ttl_hours=_read_int("WEBAPP_INVITATION_TTL_HOURS", 24),
            password_reset_ttl_minutes=_read_int(
                "WEBAPP_PASSWORD_RESET_TTL_MINUTES", 30
            ),
            password_min_length=_read_int("WEBAPP_PASSWORD_MIN_LENGTH", 12, 10),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        self._validate_mail_settings()
        if not self.production:
            return
        self._validate_production_security()
        self._validate_production_mail()

    def _validate_mail_settings(self) -> None:
        if self.mail_provider not in {"console", "smtp"}:
            raise ValueError("WEBAPP_MAIL_PROVIDER 只支持 console 或 smtp")
        if self.smtp_use_tls and self.smtp_use_ssl:
            raise ValueError("WEBAPP_SMTP_USE_TLS 和 WEBAPP_SMTP_USE_SSL 不能同时启用")

    def _validate_production_security(self) -> None:
        if (
            self.bootstrap_password == "change-me-now"
            or self.bootstrap_password.startswith("请替换")
            or len(self.bootstrap_password) < 14
        ):
            raise ValueError("生产环境必须设置至少 14 位初始密码")
        if (
            "@" not in self.bootstrap_email
            or self.bootstrap_email.startswith("@")
            or self.bootstrap_email.endswith("@")
        ):
            raise ValueError("生产环境必须设置有效的初始管理员邮箱")
        if not self.bootstrap_name:
            raise ValueError("生产环境必须设置初始管理员名称")
        if not self.encryption_key:
            raise ValueError("生产环境必须设置 WEBAPP_ENCRYPTION_KEY")
        if not self.secure_cookies:
            raise ValueError("生产环境必须启用 WEBAPP_SECURE_COOKIES")
        if self.task_workers < 15:
            raise ValueError(
                "生产环境至少需要 15 个 Listing 槽位，以支持 5 个用户各并行 3 个片段"
            )
        if not self.database_path.is_relative_to(self.data_dir):
            raise ValueError("生产环境数据库必须位于 WEBAPP_DATA_DIR 内")

    def _validate_production_mail(self) -> None:
        if not self.public_web_url.startswith("https://"):
            raise ValueError("生产环境 WEBAPP_PUBLIC_URL 必须使用 HTTPS")
        if self.mail_provider != "smtp":
            raise ValueError("生产环境必须设置 WEBAPP_MAIL_PROVIDER=smtp")
        if not self.smtp_host:
            raise ValueError("生产环境必须设置 WEBAPP_SMTP_HOST")
        if not self.smtp_from:
            raise ValueError("生产环境必须设置 WEBAPP_SMTP_FROM")

    def ensure_directories(self) -> None:
        for name in RUNTIME_DIRECTORIES:
            (self.data_dir / name).mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
