from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from scripts import server_release

COMMIT = "a" * 40
IMAGE_ID = "sha256:" + "b" * 64


def test_write_tag_preserves_other_env_values_and_permissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_bytes(b"SECRET=example-only\r\nAPP_IMAGE_TAG=old\r\n")
    env_file.chmod(0o600)
    monkeypatch.setattr(server_release, "ENV_FILE", env_file)

    server_release.write_tag(COMMIT)

    assert env_file.read_bytes() == (
        f"SECRET=example-only\r\nAPP_IMAGE_TAG={COMMIT}\r\n".encode()
    )
    if os.name != "nt":
        assert stat.S_IMODE(env_file.stat().st_mode) == 0o600


def test_deploy_builds_commit_image_and_updates_both_services(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("APP_IMAGE_TAG=old\n", encoding="utf-8")
    monkeypatch.setattr(server_release, "ENV_FILE", env_file)
    commands: list[tuple[tuple[str, ...], str | None]] = []

    def fake_run(*command: str, tag: str | None = None) -> str:
        commands.append((command, tag))
        if "run" in command:
            assert server_release.configured_tag() == "old"
            return ""
        if command[:3] == ("docker", "image", "inspect"):
            return f"{IMAGE_ID}|{COMMIT}"
        if command[:3] == ("docker", "compose", "-f") and "ps" in command:
            return f"{command[-1]}-container"
        if command[:2] == ("docker", "inspect"):
            return f"{IMAGE_ID}|running|healthy"
        return ""

    monkeypatch.setattr(server_release, "run_command", fake_run)

    server_release.deploy(COMMIT)

    assert server_release.configured_tag() == COMMIT
    build = next(
        command for command, _tag in commands if command[:2] == ("docker", "build")
    )
    assert f"{server_release.REVISION_LABEL}={COMMIT}" in build
    assert f"{server_release.IMAGE_NAME}:{COMMIT}" in build
    preflight, preflight_tag = next(
        (command, tag) for command, tag in commands if "run" in command
    )
    assert preflight[-3:] == (
        "-m",
        "web_backend.upgrade_database",
        "--check-only",
    )
    assert "--no-deps" in preflight
    assert preflight_tag == COMMIT
    compose_up, tag = next(
        (command, tag) for command, tag in commands if "up" in command
    )
    assert compose_up[-2:] == ("app", "backup")
    assert "--no-build" in compose_up
    assert "--wait" in compose_up
    assert tag == COMMIT


def test_deploy_allows_first_release_without_previous_tag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER=example-only\n", encoding="utf-8")
    monkeypatch.setattr(server_release, "ENV_FILE", env_file)

    def fake_run(*command: str, tag: str | None = None) -> str:
        if command[:3] == ("docker", "image", "inspect"):
            return f"{IMAGE_ID}|{COMMIT}"
        if "ps" in command:
            return f"{command[-1]}-container"
        if command[:2] == ("docker", "inspect"):
            return f"{IMAGE_ID}|running|healthy"
        return ""

    monkeypatch.setattr(server_release, "run_command", fake_run)

    server_release.deploy(COMMIT)

    assert server_release.configured_tag() == COMMIT


def test_deploy_preflight_failure_keeps_old_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("APP_IMAGE_TAG=old\n", encoding="utf-8")
    monkeypatch.setattr(server_release, "ENV_FILE", env_file)
    commands: list[tuple[str, ...]] = []

    def fake_run(*command: str, tag: str | None = None) -> str:
        commands.append(command)
        if command[:3] == ("docker", "image", "inspect"):
            return f"{IMAGE_ID}|{COMMIT}"
        if "run" in command:
            raise RuntimeError("数据库结构不匹配")
        return ""

    monkeypatch.setattr(server_release, "run_command", fake_run)

    with pytest.raises(RuntimeError, match="预检未通过"):
        server_release.deploy(COMMIT)

    assert server_release.configured_tag() == "old"
    assert not any("up" in command for command in commands)


def test_deploy_start_failure_restores_old_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_commit = "c" * 40
    old_image_id = "sha256:" + "d" * 64
    env_file = tmp_path / ".env"
    env_file.write_text(f"APP_IMAGE_TAG={old_commit}\n", encoding="utf-8")
    monkeypatch.setattr(server_release, "ENV_FILE", env_file)
    started_tags: list[str | None] = []

    def fake_run(*command: str, tag: str | None = None) -> str:
        if command[:3] == ("docker", "image", "inspect"):
            revision = command[-1].rsplit(":", 1)[-1]
            identity = IMAGE_ID if revision == COMMIT else old_image_id
            return f"{identity}|{revision}"
        if "up" in command:
            started_tags.append(tag)
            if tag == COMMIT:
                raise RuntimeError("新容器启动失败")
            return ""
        if "ps" in command:
            return f"{command[-1]}-container"
        if command[:2] == ("docker", "inspect"):
            return f"{old_image_id}|running|healthy"
        return ""

    monkeypatch.setattr(server_release, "run_command", fake_run)

    with pytest.raises(RuntimeError, match="已恢复旧版本"):
        server_release.deploy(COMMIT)

    assert started_tags == [COMMIT, old_commit]
    assert server_release.configured_tag() == old_commit


def test_deploy_reports_when_old_release_cannot_be_restored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_commit = "c" * 40
    env_file = tmp_path / ".env"
    env_file.write_text(f"APP_IMAGE_TAG={old_commit}\n", encoding="utf-8")
    monkeypatch.setattr(server_release, "ENV_FILE", env_file)
    started_tags: list[str | None] = []

    def fake_run(*command: str, tag: str | None = None) -> str:
        if command[:3] == ("docker", "image", "inspect"):
            return f"{IMAGE_ID}|{COMMIT}"
        if "up" in command:
            started_tags.append(tag)
            raise RuntimeError("容器启动失败")
        return ""

    monkeypatch.setattr(server_release, "run_command", fake_run)

    with pytest.raises(RuntimeError, match="旧版本恢复也未通过检查"):
        server_release.deploy(COMMIT)

    assert started_tags == [COMMIT, old_commit]
    assert server_release.configured_tag() == old_commit


@pytest.mark.parametrize(
    ("service", "state", "message"),
    [
        ("app", f"{IMAGE_ID}|running|unhealthy", "健康检查"),
        ("backup", "sha256:old|running|", "镜像"),
    ],
)
def test_check_release_rejects_container_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    service: str,
    state: str,
    message: str,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"APP_IMAGE_TAG={COMMIT}\n", encoding="utf-8")
    monkeypatch.setattr(server_release, "ENV_FILE", env_file)

    def fake_run(*command: str, tag: str | None = None) -> str:
        if command[:3] == ("docker", "image", "inspect"):
            return f"{IMAGE_ID}|{COMMIT}"
        if "ps" in command:
            return f"{command[-1]}-container"
        if command[:2] == ("docker", "inspect"):
            if command[-1] == f"{service}-container":
                return state
            return f"{IMAGE_ID}|running|healthy"
        raise AssertionError(command)

    monkeypatch.setattr(server_release, "run_command", fake_run)

    with pytest.raises(RuntimeError, match=message):
        server_release.check_release(COMMIT)


def test_check_release_rejects_stale_env_tag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("APP_IMAGE_TAG=old\n", encoding="utf-8")
    monkeypatch.setattr(server_release, "ENV_FILE", env_file)

    with pytest.raises(RuntimeError, match="APP_IMAGE_TAG"):
        server_release.check_release(COMMIT)
