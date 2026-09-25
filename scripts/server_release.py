from __future__ import annotations

import argparse
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"
IMAGE_NAME = "user-feedback-semantics"
REVISION_LABEL = "org.opencontainers.image.revision"
COMPOSE_FILES = ("-f", "compose.yaml", "-f", "compose.server.yaml")
TAG_LINE = re.compile(r"^\s*APP_IMAGE_TAG\s*=")


def run_command(*command: str, tag: str | None = None) -> str:
    environment = os.environ.copy()
    if tag is not None:
        environment["APP_IMAGE_TAG"] = tag
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            f"命令执行失败（退出码 {completed.returncode}）：{' '.join(command)}"
        )
    return completed.stdout.strip()


def current_commit() -> str:
    if run_command("git", "status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("工作区存在未提交文件，请先处理后再发布或核对版本")
    commit = run_command("git", "rev-parse", "--verify", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        raise RuntimeError("无法读取有效的 Git 提交号")
    return commit


def env_lines() -> tuple[str, list[str], list[int]]:
    if not ENV_FILE.is_file():
        raise RuntimeError("缺少服务器 .env 文件")
    with ENV_FILE.open(encoding="utf-8", newline="") as source:
        content = source.read()
    lines = content.splitlines(keepends=True)
    positions = [index for index, line in enumerate(lines) if TAG_LINE.match(line)]
    if len(positions) > 1:
        raise RuntimeError(".env 中存在多个 APP_IMAGE_TAG")
    return content, lines, positions


def configured_tag() -> str:
    _content, lines, positions = env_lines()
    if not positions:
        raise RuntimeError(".env 中缺少 APP_IMAGE_TAG")
    return lines[positions[0]].split("=", 1)[1].strip().strip("\"'")


def write_tag(tag: str) -> None:
    content, lines, positions = env_lines()
    newline = "\r\n" if "\r\n" in content else "\n"
    if positions:
        index = positions[0]
        ending = (
            "\r\n"
            if lines[index].endswith("\r\n")
            else ("\n" if lines[index].endswith("\n") else "")
        )
        lines[index] = f"APP_IMAGE_TAG={tag}{ending}"
    else:
        separator = "" if not content or content.endswith(("\r", "\n")) else newline
        lines.append(f"{separator}APP_IMAGE_TAG={tag}{newline}")
    updated = "".join(lines)
    if updated == content:
        return
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=".env.",
            dir=ENV_FILE.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(updated)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_path, stat.S_IMODE(ENV_FILE.stat().st_mode))
        os.replace(temporary_path, ENV_FILE)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def image_id(commit: str) -> str:
    reference = f"{IMAGE_NAME}:{commit}"
    output = run_command(
        "docker",
        "image",
        "inspect",
        "--format",
        f'{{{{.Id}}}}|{{{{index .Config.Labels "{REVISION_LABEL}"}}}}',
        reference,
    )
    identity, separator, revision = output.partition("|")
    if not separator or revision != commit:
        raise RuntimeError("镜像标记的提交号与当前代码不一致")
    return identity


def check_container(service: str, expected_image_id: str, tag: str) -> None:
    container_ids = run_command(
        "docker", "compose", *COMPOSE_FILES, "ps", "-q", service, tag=tag
    ).splitlines()
    if len(container_ids) != 1:
        raise RuntimeError(f"{service} 容器数量不是 1")
    state = run_command(
        "docker",
        "inspect",
        "--format",
        "{{.Image}}|{{.State.Status}}|"
        "{{if .State.Health}}{{.State.Health.Status}}{{end}}",
        container_ids[0],
    ).split("|")
    if len(state) != 3 or state[0] != expected_image_id:
        raise RuntimeError(f"{service} 容器使用的镜像与发布标签不一致")
    if state[1] != "running":
        raise RuntimeError(f"{service} 容器未运行")
    if service == "app" and state[2] != "healthy":
        raise RuntimeError("app 容器健康检查未通过")


def check_release(commit: str) -> None:
    tag = configured_tag()
    if tag != commit:
        raise RuntimeError(".env 中的 APP_IMAGE_TAG 与当前 Git 提交不一致")
    expected_image_id = image_id(commit)
    for service in ("app", "backup"):
        check_container(service, expected_image_id, tag)


def deploy(commit: str) -> None:
    env_lines()
    reference = f"{IMAGE_NAME}:{commit}"
    print(f"构建提交 {commit} 的镜像", flush=True)
    run_command(
        "docker",
        "build",
        "--label",
        f"{REVISION_LABEL}={commit}",
        "-t",
        reference,
        ".",
    )
    image_id(commit)
    write_tag(commit)
    print("更新 app 和 backup 容器", flush=True)
    run_command(
        "docker",
        "compose",
        *COMPOSE_FILES,
        "up",
        "-d",
        "--no-build",
        "--wait",
        "--wait-timeout",
        "120",
        "app",
        "backup",
        tag=commit,
    )
    check_release(commit)


def main() -> int:
    parser = argparse.ArgumentParser(description="核对或发布服务器代码与容器版本")
    parser.add_argument("action", choices=("check", "deploy"))
    action = parser.parse_args().action
    try:
        commit = current_commit()
        if action == "deploy":
            deploy(commit)
        else:
            check_release(commit)
    except (OSError, RuntimeError) as error:
        parser.exit(1, f"发布一致性检查失败：{error}\n")
    print(f"发布一致：{commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
