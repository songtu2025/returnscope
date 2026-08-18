from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
from pathlib import Path

from cryptography.fernet import Fernet

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "Dockerfile",
    "compose.yaml",
    "Caddyfile",
    "requirements-prod.txt",
    "web-prototype/package.json",
    "web-prototype/package-lock.json",
)


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key.strip():
            raise ValueError(f"环境文件第 {line_number} 行格式不正确")
        clean_key = key.strip()
        if clean_key in values:
            raise ValueError(f"环境变量重复：{clean_key}")
        values[clean_key] = value.strip()
    return values


def validate_environment(values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    domain = values.get("APP_DOMAIN", "")
    if (
        not domain
        or "://" in domain
        or "/" in domain
        or "." not in domain
        or any(character.isspace() for character in domain)
    ):
        errors.append("APP_DOMAIN 必须是有效域名，且不能包含协议或路径")

    email = values.get("WEBAPP_BOOTSTRAP_EMAIL", "")
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        errors.append("WEBAPP_BOOTSTRAP_EMAIL 必须是有效邮箱")
    if not values.get("WEBAPP_BOOTSTRAP_NAME", "").strip():
        errors.append("WEBAPP_BOOTSTRAP_NAME 不能为空")

    password = values.get("WEBAPP_BOOTSTRAP_PASSWORD", "")
    if (
        len(password) < 14
        or password == "change-me-now"
        or password.startswith("请替换")
    ):
        errors.append("WEBAPP_BOOTSTRAP_PASSWORD 必须是至少 14 位的真实密码")

    encryption_key = values.get("WEBAPP_ENCRYPTION_KEY", "")
    try:
        Fernet(encryption_key.encode("ascii"))
    except (UnicodeEncodeError, ValueError):
        errors.append("WEBAPP_ENCRYPTION_KEY 必须是有效 Fernet 密钥")

    integer_rules = (
        ("WEBAPP_SESSION_DAYS", 1),
        ("WEBAPP_TASK_WORKERS", 15),
        ("WEBAPP_BACKUP_RETENTION_DAYS", 1),
    )
    for key, minimum in integer_rules:
        try:
            value = int(values.get(key, ""))
        except ValueError:
            errors.append(f"{key} 必须是整数")
            continue
        if value < minimum:
            errors.append(f"{key} 不能小于 {minimum}")
    return errors


def validate_project(project_root: Path) -> list[str]:
    return [
        f"缺少部署文件：{relative_path}"
        for relative_path in REQUIRED_FILES
        if not (project_root / relative_path).is_file()
    ]


def validate_permissions(env_file: Path) -> list[str]:
    if os.name == "nt":
        return []
    mode = stat.S_IMODE(env_file.stat().st_mode)
    if mode & 0o077:
        return ["生产环境文件权限过宽，请执行 chmod 600"]
    return []


def validate_docker(env_file: Path, project_root: Path) -> list[str]:
    docker = shutil.which("docker")
    if docker is None:
        return ["未找到 Docker，请先安装 Docker Engine 与 Compose 插件"]
    commands = (
        [docker, "compose", "version"],
        [
            docker,
            "compose",
            "--env-file",
            str(env_file),
            "config",
            "--quiet",
        ],
    )
    errors: list[str] = []
    for command in commands:
        result = subprocess.run(
            command,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            errors.append(message or "Docker Compose 校验失败")
            break
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="检查 Web 生产部署条件")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=PROJECT_ROOT / ".env.production",
    )
    parser.add_argument("--skip-docker", action="store_true")
    args = parser.parse_args()
    env_file = args.env_file.resolve()
    if not env_file.is_file():
        raise SystemExit(f"生产环境文件不存在：{env_file}")
    try:
        values = read_env_file(env_file)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    errors = [
        *validate_environment(values),
        *validate_project(PROJECT_ROOT),
        *validate_permissions(env_file),
    ]
    if not args.skip_docker:
        errors.extend(validate_docker(env_file, PROJECT_ROOT))
    if errors:
        for error in errors:
            print(f"[失败] {error}")
        raise SystemExit(1)
    print("生产部署预检通过")


if __name__ == "__main__":
    main()
