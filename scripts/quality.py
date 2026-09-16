from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "web-prototype"
PYTHON_TARGETS = (
    "web_backend",
    "return_semantics",
    "return_analysis",
    "tests",
    "scripts/quality.py",
    "scripts/secret_scan.py",
)
PRODUCTION_PYTHON_TARGETS = (
    "web_backend",
    "return_semantics",
    "return_analysis",
)


def npm_command(*arguments: str) -> list[str]:
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError(
            "npm was not found. Install Node.js before running quality checks."
        )
    return [npm, *arguments]


def check_commands() -> list[tuple[str, list[str], Path]]:
    return [
        (
            "Ruff lint",
            [sys.executable, "-m", "ruff", "check", *PYTHON_TARGETS],
            PROJECT_ROOT,
        ),
        (
            "Ruff format check",
            [sys.executable, "-m", "ruff", "format", "--check", *PYTHON_TARGETS],
            PROJECT_ROOT,
        ),
        (
            "Secret scan",
            [sys.executable, "scripts/secret_scan.py"],
            PROJECT_ROOT,
        ),
        (
            "Python tests",
            [sys.executable, "-m", "pytest", "tests", "-q"],
            PROJECT_ROOT,
        ),
        (
            "Python dead-code check",
            [
                sys.executable,
                "-m",
                "vulture",
                *PRODUCTION_PYTHON_TARGETS,
                "--min-confidence",
                "100",
            ],
            PROJECT_ROOT,
        ),
        ("Frontend quality checks", npm_command("run", "quality"), FRONTEND_ROOT),
    ]


def audit_commands() -> list[tuple[str, list[str], Path]]:
    return [
        (
            "Python type audit",
            [sys.executable, "-m", "mypy"],
            PROJECT_ROOT,
        ),
        (
            "Python complexity audit",
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--select",
                "C90,PLR0912,PLR0913,PLR0915",
                *PRODUCTION_PYTHON_TARGETS,
            ],
            PROJECT_ROOT,
        ),
        ("Frontend type audit", npm_command("run", "audit:types"), FRONTEND_ROOT),
        ("Frontend export audit", npm_command("run", "audit:exports"), FRONTEND_ROOT),
    ]


def run(commands: list[tuple[str, list[str], Path]]) -> int:
    failures: list[str] = []
    environment = os.environ.copy()
    environment.setdefault("OPENAPI_PYTHON", sys.executable)
    for name, command, working_directory in commands:
        print(f"\n==> {name}", flush=True)
        completed = subprocess.run(
            command,
            cwd=working_directory,
            check=False,
            env=environment,
        )
        if completed.returncode != 0:
            failures.append(name)

    if failures:
        print(f"\nFailed: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("\nAll checks passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run project quality checks.")
    parser.add_argument(
        "mode",
        choices=("check", "audit"),
        nargs="?",
        default="check",
        help="Run blocking checks or non-blocking historical-debt audits.",
    )
    mode = parser.parse_args().mode
    try:
        commands = check_commands() if mode == "check" else audit_commands()
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    return run(commands)


if __name__ == "__main__":
    raise SystemExit(main())
