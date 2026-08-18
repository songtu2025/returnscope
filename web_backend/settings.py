from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数") from exc
    if value < minimum:
        raise ValueError(f"{name} 不能小于 {minimum}")
    return value


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

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(
            os.getenv("WEBAPP_DATA_DIR", PROJECT_ROOT / "runtime")
        ).resolve()
        database_path = Path(
            os.getenv("WEBAPP_DATABASE_PATH", data_dir / "app.db")
        ).resolve()
        settings = cls(
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
            secure_cookies=os.getenv(
                "WEBAPP_SECURE_COOKIES",
                "false",
            ).lower()
            in {"1", "true", "yes", "on"},
            production=os.getenv(
                "WEBAPP_PRODUCTION",
                "false",
            ).lower()
            in {"1", "true", "yes", "on"},
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.production:
            return
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

    def ensure_directories(self) -> None:
        for name in ("uploads", "results", "cache"):
            (self.data_dir / name).mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
