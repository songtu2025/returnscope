from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.secret_scan_content import Finding as Finding
from scripts.secret_scan_content import scan_content as scan_content
from scripts.secret_scan_git import scan_repository as scan_repository

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
