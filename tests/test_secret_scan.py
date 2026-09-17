from __future__ import annotations

import os
import subprocess
import tempfile
from io import StringIO
from pathlib import Path

from scripts.secret_scan import Finding, scan_content, scan_repository, write_report


def run_git(repository: Path, *arguments: str) -> None:
    run_git_output(repository, *arguments)


def run_git_output(
    repository: Path,
    *arguments: str,
    input_data: bytes | None = None,
    environment: dict[str, str] | None = None,
) -> bytes:
    command_environment = None
    if environment is not None:
        command_environment = {**os.environ, **environment}
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=command_environment,
    )
    return completed.stdout


def initialize_repository(repository: Path) -> None:
    run_git(repository, "init", "--quiet")
    run_git(repository, "config", "user.name", "Quality Test")
    run_git(repository, "config", "user.email", "quality@example.invalid")
    run_git(repository, "commit", "--allow-empty", "--quiet", "-m", "initial")


def varied_value(length: int) -> str:
    alphabet = "Ab3Cd5Ef7Gh9Jk2Lm4Np6Qr8St0UvWxYz"
    return (alphabet * ((length // len(alphabet)) + 1))[:length]


def commit_blob_ref(
    repository: Path,
    ref: str,
    path: str,
    content: bytes,
    *,
    tag: bool = False,
) -> None:
    blob = run_git_output(
        repository,
        "hash-object",
        "-w",
        "--stdin",
        input_data=content,
    ).strip()
    with tempfile.TemporaryDirectory(
        prefix="fixture-index-",
        dir=repository / ".git",
    ) as index_directory:
        index_file = Path(index_directory) / "index"
        environment = {"GIT_INDEX_FILE": str(index_file)}
        run_git_output(
            repository,
            "update-index",
            "--add",
            "--cacheinfo",
            f"100644,{blob.decode('ascii')},{path}",
            environment=environment,
        )
        tree = run_git_output(
            repository,
            "write-tree",
            environment=environment,
        ).strip()
    commit = run_git_output(
        repository,
        "commit-tree",
        tree.decode("ascii"),
        "-m",
        "fixture",
    ).strip()
    if tag:
        run_git(repository, "tag", ref, commit.decode("ascii"))
    else:
        run_git(repository, "update-ref", ref, commit.decode("ascii"))


def has_finding(
    findings: list[Finding],
    rule: str,
    *,
    location: str | None = None,
    location_prefix: str | None = None,
) -> bool:
    return any(
        finding.rule == rule
        and (location is None or finding.location == location)
        and (location_prefix is None or finding.location.startswith(location_prefix))
        for finding in findings
    )


def test_detects_supported_secret_shapes() -> None:
    cases = {
        "private-key": "-----BEGIN RSA " + "PRIVATE KEY-----",
        "aws-access-key": "AKIA" + varied_value(16).upper(),
        "openai-api-key": "sk-proj-" + varied_value(48),
        "github-token": "ghp_" + varied_value(36),
        "gitlab-token": "glpat-" + varied_value(32),
        "slack-token": "xoxb-" + varied_value(32),
        "google-api-key": "AIza" + varied_value(35),
    }

    for expected_rule, secret in cases.items():
        findings = scan_content(f"credential={secret}\n".encode(), "current:file")
        assert [finding.rule for finding in findings] == [expected_rule]


def test_context_words_do_not_hide_high_entropy_secret() -> None:
    secret = "sk-proj-" + varied_value(48)
    data = f"test_api_key={secret} sample example\n".encode()

    findings = scan_content(data, "current:file")

    assert [finding.rule for finding in findings] == ["openai-api-key"]


def test_finds_current_and_history_without_leaking_values(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    historical_secret = "sk-proj-" + varied_value(48)
    historical_file = tmp_path / "historical.txt"
    historical_file.write_text(f"api_key={historical_secret}\n", encoding="utf-8")
    run_git(tmp_path, "add", "historical.txt")
    commit_secret = "glpat-" + varied_value(32)
    run_git(tmp_path, "commit", "--quiet", "-m", f"credential={commit_secret}")
    historical_file.unlink()
    run_git(tmp_path, "add", "--all")
    run_git(tmp_path, "commit", "--quiet", "-m", "remove data")

    current_secret = "ghp_" + varied_value(36)
    (tmp_path / "current.txt").write_text(f"token={current_secret}\n", encoding="utf-8")

    findings = scan_repository(tmp_path)
    report = StringIO()
    write_report(findings, report)
    output = report.getvalue()

    assert has_finding(findings, "openai-api-key", location_prefix="history:")
    assert has_finding(findings, "github-token", location="current:current.txt")
    assert has_finding(findings, "gitlab-token", location_prefix="history:")
    assert historical_secret not in output
    assert current_secret not in output
    assert commit_secret not in output

    secret_named_file = tmp_path / f"{current_secret}.txt"
    secret_named_file.write_text(f"token={current_secret}\n", encoding="utf-8")
    redacted_report = StringIO()
    write_report(scan_repository(tmp_path), redacted_report)
    assert current_secret not in redacted_report.getvalue()


def test_ignores_secrets_only_reachable_from_codex_refs(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    codex_secret = "sk-proj-" + varied_value(48)
    commit_blob_ref(
        tmp_path,
        "refs/codex/turn-diffs/test",
        "historical-samples/node_modules/tesseract.js/generated.js",
        f"api_key={codex_secret}\n".encode(),
    )

    findings = scan_repository(tmp_path)
    report = StringIO()
    write_report(findings, report)

    assert findings == []
    assert codex_secret not in report.getvalue()


def test_scans_branch_and_tag_history(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    branch_secret = "sk-proj-" + varied_value(48)
    tag_secret = "ghp_" + varied_value(36)
    commit_blob_ref(
        tmp_path,
        "refs/heads/feature/secret-history",
        "branch-secret.txt",
        f"api_key={branch_secret}\n".encode(),
    )
    commit_blob_ref(
        tmp_path,
        "v1.0.0",
        "tag-secret.txt",
        f"token={tag_secret}\n".encode(),
        tag=True,
    )
    branch_tree = run_git_output(
        tmp_path,
        "ls-tree",
        "--name-only",
        "refs/heads/feature/secret-history",
    ).decode("utf-8")
    tag_tree = run_git_output(
        tmp_path,
        "ls-tree",
        "--name-only",
        "refs/tags/v1.0.0",
    ).decode("utf-8")

    findings = scan_repository(tmp_path)
    report = StringIO()
    write_report(findings, report)
    output = report.getvalue()

    assert branch_tree.splitlines() == ["branch-secret.txt"]
    assert tag_tree.splitlines() == ["tag-secret.txt"]
    assert has_finding(findings, "openai-api-key", location_prefix="history:")
    assert has_finding(findings, "github-token", location_prefix="history:")
    assert branch_secret not in output
    assert tag_secret not in output


def test_scans_tracked_ignored_and_skips_untracked_ignored_files(
    tmp_path: Path,
) -> None:
    initialize_repository(tmp_path)
    placeholder = "sk-proj-" + "A" * 48
    (tmp_path / "settings.example").write_text(
        f"OPENAI_API_KEY=placeholder-{placeholder}\n", encoding="utf-8"
    )
    tracked_directory = tmp_path / "tracked-data"
    tracked_directory.mkdir()
    tracked_file = tracked_directory / "credentials.txt"
    tracked_file.write_text("safe\n", encoding="utf-8")
    run_git(tmp_path, "add", "tracked-data/credentials.txt")
    run_git(tmp_path, "commit", "--quiet", "-m", "add fixture")

    (tmp_path / ".gitignore").write_text(
        "ignored-data/\ntracked-data/\n", encoding="utf-8"
    )
    tracked_secret = "xoxb-" + varied_value(32)
    tracked_file.write_text(f"token={tracked_secret}\n", encoding="utf-8")
    ignored_directory = tmp_path / "ignored-data"
    ignored_directory.mkdir()
    ignored_secret = "glpat-" + varied_value(32)
    (ignored_directory / "credentials.txt").write_text(
        f"token={ignored_secret}\n", encoding="utf-8"
    )

    findings = scan_repository(tmp_path)

    assert [
        (finding.rule, finding.location, finding.count) for finding in findings
    ] == [("slack-token", "current:tracked-data/credentials.txt", 1)]


def test_skips_binary_files(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    secret = ("AIza" + varied_value(35)).encode()
    (tmp_path / "artifact.bin").write_bytes(b"\0\x01\x02" + secret)

    findings = scan_repository(tmp_path)

    assert findings == []
