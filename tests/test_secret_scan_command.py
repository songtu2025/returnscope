from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "mode, expected_code", [("clean", 0), ("finding", 1), ("invalid-root", 2)]
)
def test_secret_scan_command_preserves_exit_codes_without_leaking_values(
    tmp_path: Path, mode: str, expected_code: int
) -> None:
    root = tmp_path / "repository"
    if mode != "invalid-root":
        subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    synthetic_value = "sk-proj-" + "Ab3Cd5Ef7Gh9Jk2Lm4Np6Qr8St0UvWxYz" * 2
    if mode == "finding":
        (root / "synthetic.txt").write_text(synthetic_value, encoding="utf-8")
    script = Path(__file__).parents[1] / "scripts/secret_scan.py"

    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-I", str(script), "--root", str(root)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == expected_code
    assert synthetic_value not in result.stdout + result.stderr
    if mode == "clean":
        assert result.stdout.strip() == "Secret scan passed."
    elif mode == "finding":
        assert "openai-api-key: current:synthetic.txt: 1" in result.stdout
    else:
        assert "Secret scan failed:" in result.stderr
