from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import return_semantics_cli_runtime as runtime
from scripts import run_return_semantics as cli
from scripts.return_semantics_cli_options import validate_args
from scripts.run_return_semantics import (
    load_standard_taxonomy,
    parse_args,
    resolve_database_path,
)


def test_cli_defaults_to_database_footwear_standard(tmp_path: Path) -> None:
    database_path = tmp_path / "app.db"
    args = parse_args(
        [
            "--store",
            "SEEKWAY:US",
            "--database",
            str(database_path),
        ]
    )

    taxonomy, version = load_standard_taxonomy(
        args.database,
        args.standard_id,
        args.standard_version_id,
    )

    assert not hasattr(args, "taxonomy")
    assert version["standard_key"] == "footwear"
    assert version["status"] == "published"
    assert taxonomy.version == version["taxonomy_version"]


def test_cli_can_pin_an_immutable_standard_version(tmp_path: Path) -> None:
    database_path = tmp_path / "app.db"
    _taxonomy, current = load_standard_taxonomy(
        database_path,
        "classification_standard_footwear",
        None,
    )

    taxonomy, pinned = load_standard_taxonomy(
        database_path,
        "classification_standard_footwear",
        str(current["id"]),
    )

    assert pinned["id"] == current["id"]
    assert taxonomy.version == current["taxonomy_version"]


def test_cli_defaults_to_web_model_configuration(tmp_path: Path) -> None:
    database_path = tmp_path / "app.db"
    args = parse_args(["--store", "SEEKWAY:US", "--database", str(database_path)])

    assert args.model_config_source == "web"
    assert resolve_database_path(args.database, args.dotenv) == database_path.resolve()


def test_cli_env_model_configuration_must_be_explicit() -> None:
    args = parse_args(
        [
            "--store",
            "SEEKWAY:US",
            "--model-config-source",
            "env",
        ]
    )

    assert args.model_config_source == "env"


@pytest.mark.parametrize(
    "arguments, message",
    [
        (["--store", " "], "--store 不能为空"),
        (["--store", "synthetic", "--claims", "claims.json"], "--claims 必须与"),
        (["--store", "synthetic", "--offset", "-1"], "--offset 不能小于"),
        (["--store", "synthetic", "--limit", "0"], "--limit 必须大于"),
    ],
)
def test_cli_rejects_invalid_scope_before_loading_data(
    arguments: list[str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_args(parse_args(arguments))


def test_cli_dry_run_does_not_build_model_or_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arguments = parse_args(["--store", "synthetic", "--dry-run"])
    monkeypatch.setattr(cli, "parse_args", lambda: arguments)
    monkeypatch.setattr(cli, "resolve_database_path", lambda *_: tmp_path / "app.db")
    standard = {"standard_name": "synthetic", "version_no": 1, "id": "version-1"}
    monkeypatch.setattr(cli, "load_standard_taxonomy", lambda *_: (object(), standard))
    records = {"has_text_evidence": SimpleNamespace(sum=lambda: 2)}
    dataset = SimpleNamespace(mskus=["synthetic"], records=records, unique_comments=[])
    loader = Mock(return_value=dataset)
    model = Mock(side_effect=AssertionError("预览不得构建模型"))
    exporter = Mock(side_effect=AssertionError("预览不得导出结果"))
    monkeypatch.setattr(cli, "load_return_dataset", loader)
    monkeypatch.setattr(cli, "build_model_runtime", model)
    monkeypatch.setattr(cli, "export_results", exporter)

    cli.main()

    assert loader.call_args.kwargs == {"store": "synthetic", "listing": None}
    model.assert_not_called()
    exporter.assert_not_called()


def test_cli_model_policy_uses_explicit_environment_source_and_review_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = SimpleNamespace(
        model="primary",
        reasoning_effort="low",
        cheap_model=None,
        cheap_reasoning_effort=None,
        secondary_model="old-review",
        secondary_reasoning_effort="medium",
    )
    create = Mock(return_value=SimpleNamespace(settings=settings))
    resolve = Mock(return_value={"version": "synthetic-policy"})
    effective = object()
    apply_policy = Mock(return_value=effective)
    client = Mock(return_value=object())
    monkeypatch.setattr(runtime, "create_model_client", create)
    monkeypatch.setattr(
        runtime.ClassificationStandardService,
        "_capability_from_snapshot",
        lambda _: "synthetic-capability",
    )
    monkeypatch.setattr(runtime, "resolve_model_policy", resolve)
    monkeypatch.setattr(runtime.AgentRunner, "_settings_for_model_policy", apply_policy)
    monkeypatch.setattr(runtime, "Sub2APIClient", client)
    dotenv = tmp_path / "synthetic.env"

    result, policy = runtime.build_model_runtime(
        database_path=tmp_path / "app.db",
        dotenv_path=dotenv,
        source="env",
        user_id=None,
        standard_version={"snapshot": {}},
        secondary_model="new-review",
    )

    create.assert_called_once_with(dotenv)
    assert resolve.call_args.args[0] == "synthetic-capability"
    assert resolve.call_args.args[1]["secondary_model"] == "new-review"
    assert resolve.call_args.args[1]["primary_model"] == "primary"
    apply_policy.assert_called_once_with(settings, policy)
    client.assert_called_once_with(effective)
    assert result is client.return_value


def test_cli_help_works_from_another_directory(tmp_path: Path) -> None:
    script = Path(__file__).parents[1] / "scripts/run_return_semantics.py"
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-I", str(script), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert "--model-config-source" in result.stdout
    assert "--standard-version-id" in result.stdout
