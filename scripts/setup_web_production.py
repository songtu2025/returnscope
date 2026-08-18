from __future__ import annotations

import argparse
import secrets
from pathlib import Path

from cryptography.fernet import Fernet

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成 Web 生产部署所需的安全环境变量",
    )
    parser.add_argument("--domain", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="系统管理员")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / ".env.production",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"配置文件已存在，不会覆盖：{output}")
    password = secrets.token_urlsafe(18)
    encryption_key = Fernet.generate_key().decode("ascii")
    values = {
        "APP_DOMAIN": args.domain.strip(),
        "WEBAPP_BOOTSTRAP_EMAIL": args.email.strip().lower(),
        "WEBAPP_BOOTSTRAP_NAME": args.name.strip(),
        "WEBAPP_BOOTSTRAP_PASSWORD": password,
        "WEBAPP_ENCRYPTION_KEY": encryption_key,
        "WEBAPP_SESSION_DAYS": "14",
        "WEBAPP_TASK_WORKERS": "15",
        "WEBAPP_BACKUP_RETENTION_DAYS": "14",
    }
    output.write_text(
        "\n".join(f"{key}={value}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )
    output.chmod(0o600)
    print(f"已生成：{output}")
    print(f"管理员初始密码：{password}")


if __name__ == "__main__":
    main()
