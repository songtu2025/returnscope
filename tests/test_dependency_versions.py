from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _production_dependencies() -> list[tuple[str, str]]:
    dependencies: list[tuple[str, str]] = []
    for raw_line in (
        (PROJECT_ROOT / "requirements-prod.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    ):
        requirement = raw_line.partition("#")[0].strip()
        if not requirement or "==" not in requirement:
            continue
        package, expected = requirement.split("==", maxsplit=1)
        dependencies.append((package.partition("[")[0], expected))
    return dependencies


def test_installed_production_dependencies_match_pinned_versions() -> None:
    mismatches: list[str] = []
    for package, expected in _production_dependencies():
        try:
            actual = version(package)
        except PackageNotFoundError:
            actual = "未安装"
        if actual != expected:
            mismatches.append(f"{package}: 期望 {expected}，实际 {actual}")

    assert not mismatches, "生产依赖版本不一致：\n" + "\n".join(mismatches)
