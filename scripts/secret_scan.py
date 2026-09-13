from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, TextIO

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SecretRule:
    name: str
    pattern: re.Pattern[bytes]


@dataclass(frozen=True, order=True)
class Finding:
    rule: str
    location: str
    count: int


RULES = (
    SecretRule(
        "private-key",
        re.compile(rb"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"),
    ),
    SecretRule(
        "aws-access-key",
        re.compile(
            rb"(?<![A-Z0-9])(?:AKIA|ASIA|AIDA|AROA|AIPA|ANPA|ANVA|ASCA)"
            rb"[A-Z0-9]{16}(?![A-Z0-9])"
        ),
    ),
    SecretRule(
        "openai-api-key",
        re.compile(
            rb"(?<![A-Za-z0-9_-])(?:sk-(?:proj|svcacct)-[A-Za-z0-9_-]{20,}"
            rb"|sk-[A-Za-z0-9]{32,})(?![A-Za-z0-9_-])"
        ),
    ),
    SecretRule(
        "github-token",
        re.compile(
            rb"(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{36,255}"
            rb"|github_pat_[A-Za-z0-9_]{60,255})(?![A-Za-z0-9_])"
        ),
    ),
    SecretRule(
        "gitlab-token",
        re.compile(
            rb"(?<![A-Za-z0-9_-])(?:glpat|glrt)-[A-Za-z0-9_-]{20,}"
            rb"(?![A-Za-z0-9_-])"
        ),
    ),
    SecretRule(
        "slack-token",
        re.compile(
            rb"(?<![A-Za-z0-9-])xox[baprs]-[A-Za-z0-9-]{10,}"
            rb"(?![A-Za-z0-9-])"
        ),
    ),
    SecretRule(
        "google-api-key",
        re.compile(rb"(?<![A-Za-z0-9_-])AIza[A-Za-z0-9_-]{35}(?![A-Za-z0-9_-])"),
    ),
)

PLACEHOLDER_MARKERS = (
    b"placeholder",
    b"example",
    b"sample",
    b"fake",
    b"dummy",
    b"test",
    b"redacted",
    b"changeme",
    b"replace-me",
    b"replace_me",
    b"not-a-real",
    b"not_real",
    b"your-",
)
TOKEN_PREFIXES = (
    b"sk-proj-",
    b"sk-svcacct-",
    b"github_pat_",
    b"glpat-",
    b"glrt-",
    b"xoxb-",
    b"xoxa-",
    b"xoxp-",
    b"xoxr-",
    b"xoxs-",
    b"ghp_",
    b"gho_",
    b"ghu_",
    b"ghs_",
    b"ghr_",
    b"sk-",
    b"AIza",
)
AWS_PREFIXES = (b"AKIA", b"ASIA", b"AIDA", b"AROA", b"AIPA", b"ANPA", b"ANVA", b"ASCA")
SCANNED_GIT_OBJECT_TYPES = {b"blob", b"commit", b"tag"}
HISTORY_REF_PREFIXES = ("refs/heads", "refs/remotes", "refs/tags")


def _run_git(root: Path, *arguments: str, input_data: bytes | None = None) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as error:
        raise RuntimeError("git was not found") from error
    if completed.returncode != 0:
        command = " ".join(arguments[:2])
        raise RuntimeError(f"git {command} failed")
    return completed.stdout


def _is_binary(data: bytes) -> bool:
    sample = data[:8192]
    if b"\0" in sample:
        return True
    control_bytes = sum(byte < 32 and byte not in (9, 10, 13) for byte in sample)
    return bool(sample) and control_bytes / len(sample) > 0.3


def _payload(value: bytes) -> bytes:
    lower_value = value.lower()
    for prefix in TOKEN_PREFIXES:
        if lower_value.startswith(prefix.lower()):
            return value[len(prefix) :]
    upper_value = value.upper()
    if upper_value.startswith(AWS_PREFIXES):
        return value[4:]
    return value


def _looks_like_placeholder(data: bytes, start: int, end: int) -> bool:
    value = data[start:end]
    payload = _payload(value).lower().lstrip(b"-_")
    if any(payload.startswith(marker) for marker in PLACEHOLDER_MARKERS):
        return True
    normalized_payload = bytes(byte for byte in payload if chr(byte).isalnum())
    return len(normalized_payload) >= 16 and len(set(normalized_payload)) <= 4


def scan_content(data: bytes, location: str) -> list[Finding]:
    if _is_binary(data):
        return []
    counts: Counter[str] = Counter()
    for rule in RULES:
        for match in rule.pattern.finditer(data):
            if not _looks_like_placeholder(data, match.start(), match.end()):
                counts[rule.name] += 1
    return [Finding(rule, location, count) for rule, count in counts.items()]


def _safe_path(raw_path: bytes) -> str:
    redacted_path = raw_path
    for rule in RULES:
        redacted_path = rule.pattern.sub(b"[secret]", redacted_path)
    path = os.fsdecode(redacted_path).replace("\\", "/")
    return "".join(character if character.isprintable() else "?" for character in path)


def scan_current_files(root: Path) -> list[Finding]:
    output = _run_git(
        root,
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    )
    findings: list[Finding] = []
    for raw_path in output.split(b"\0"):
        if not raw_path:
            continue
        path = root / os.fsdecode(raw_path)
        if path.is_symlink() or not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError as error:
            raise RuntimeError(f"cannot read {_safe_path(raw_path)}") from error
        findings.extend(scan_content(data, f"current:{_safe_path(raw_path)}"))
    return findings


def _history_refs(root: Path) -> list[bytes]:
    refs = []
    try:
        _run_git(root, "rev-parse", "--verify", "--quiet", "HEAD")
    except RuntimeError:
        pass
    else:
        refs.append(b"HEAD")

    output = _run_git(
        root,
        "for-each-ref",
        "--format=%(refname)",
        *HISTORY_REF_PREFIXES,
    )
    refs.extend(ref for ref in output.splitlines() if ref)
    return list(dict.fromkeys(refs))


def _history_object_ids(root: Path) -> list[bytes]:
    refs = _history_refs(root)
    if not refs:
        return []
    object_lines = _run_git(
        root,
        "rev-list",
        "--objects",
        "--stdin",
        input_data=b"\n".join(refs) + b"\n",
    ).splitlines()
    object_ids = list(dict.fromkeys(line.split(maxsplit=1)[0] for line in object_lines))
    if not object_ids:
        return []
    metadata = _run_git(
        root,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_data=b"\n".join(object_ids) + b"\n",
    )
    return [
        line.split(maxsplit=2)[0]
        for line in metadata.splitlines()
        if len(line.split(maxsplit=2)) == 3
        and line.split(maxsplit=2)[1] in SCANNED_GIT_OBJECT_TYPES
    ]


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.read(size - len(chunks))
        if not chunk:
            raise RuntimeError("git cat-file returned incomplete data")
        chunks.extend(chunk)
    return bytes(chunks)


def _write_object_ids(
    stream: BinaryIO, object_ids: list[bytes], errors: list[OSError]
) -> None:
    try:
        stream.write(b"\n".join(object_ids) + b"\n")
    except OSError as error:
        errors.append(error)
    finally:
        stream.close()


def scan_history(root: Path) -> list[Finding]:
    object_ids = _history_object_ids(root)
    if not object_ids:
        return []
    process = subprocess.Popen(
        ["git", "-C", str(root), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if process.stdin is None or process.stdout is None:
        process.kill()
        raise RuntimeError("git cat-file pipes were not created")

    write_errors: list[OSError] = []
    writer = threading.Thread(
        target=_write_object_ids,
        args=(process.stdin, object_ids, write_errors),
        daemon=True,
    )
    writer.start()

    findings: list[Finding] = []
    try:
        for _ in object_ids:
            header = process.stdout.readline().split()
            if len(header) != 3 or header[1] not in SCANNED_GIT_OBJECT_TYPES:
                raise RuntimeError("git cat-file returned an invalid header")
            data = _read_exact(process.stdout, int(header[2]))
            if process.stdout.read(1) != b"\n":
                raise RuntimeError("git cat-file returned an invalid delimiter")
            location = f"history:{header[0].decode('ascii')}"
            findings.extend(scan_content(data, location))
        writer.join()
        if write_errors:
            raise RuntimeError("git cat-file input failed")
        if process.wait() != 0:
            raise RuntimeError("git cat-file failed")
    except Exception:
        process.kill()
        writer.join()
        process.wait()
        raise
    finally:
        process.stdout.close()
    return findings


def scan_repository(root: Path) -> list[Finding]:
    return sorted([*scan_current_files(root), *scan_history(root)])


def write_report(findings: list[Finding], stream: TextIO) -> None:
    for finding in findings:
        print(f"{finding.rule}: {finding.location}: {finding.count}", file=stream)
    if findings:
        count = sum(finding.count for finding in findings)
        print(f"Secret scan found {count} potential secrets.", file=stream)
    else:
        print("Secret scan passed.", file=stream)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan current repository files and Git history for secrets."
    )
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    arguments = parser.parse_args()
    try:
        findings = scan_repository(arguments.root.resolve())
    except RuntimeError as error:
        print(f"Secret scan failed: {error}", file=sys.stderr)
        return 2
    write_report(findings, sys.stdout)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
