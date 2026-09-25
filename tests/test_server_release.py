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
    compose_up, tag = next(
        (command, tag) for command, tag in commands if "up" in command
    )
    assert compose_up[-2:] == ("app", "backup")
    assert "--no-build" in compose_up
    assert "--wait" in compose_up
    assert tag == COMMIT


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
