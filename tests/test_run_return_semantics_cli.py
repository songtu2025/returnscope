from __future__ import annotations

from pathlib import Path

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
