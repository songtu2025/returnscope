from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import IO

from scripts.secret_scan_content import Finding, _safe_path, scan_content

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


def _read_exact(stream: IO[bytes], size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.read(size - len(chunks))
        if not chunk:
            raise RuntimeError("git cat-file returned incomplete data")
        chunks.extend(chunk)
    return bytes(chunks)


def _write_object_ids(
    stream: IO[bytes], object_ids: list[bytes], errors: list[OSError]
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
