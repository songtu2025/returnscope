from __future__ import annotations

import json
from pathlib import Path

from web_backend import classification_standard_bootstrap
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.database import Database


def _family(standard_key: str, taxonomy_file: str) -> dict:
    return {
        "key": standard_key,
        "agent_family": f"{standard_key}智能体",
        "logic_version": f"{standard_key}-logic-v1",
        "taxonomy": taxonomy_file,
        "model_policy": {
            "version": f"{standard_key}-policy-v1",
            "first_pass_role": "primary",
            "review_role": "secondary",
        },
        "variants": [
            {
                "category_a": "测试品类",
                "category_b": standard_key,
                "attributes": {},
            }
        ],
    }


def _write_seed(root: Path, families: list[dict], marker: str = "初始规则") -> None:
    config_dir = root / "config"
    config_dir.mkdir(exist_ok=True)
    for family in families:
        taxonomy_file = str(family["taxonomy"])
        taxonomy = {
            "version": f"{family['key']}-taxonomy-v1",
            "agent_family": family["agent_family"],
            "product_context": "测试商品",
            "allowed_parts": ["UNSPECIFIED"],
            "instructions": [marker],
            "labels": [],
        }
        (config_dir / taxonomy_file).write_text(
            json.dumps(taxonomy, ensure_ascii=False),
            encoding="utf-8",
        )
    (config_dir / "category_capabilities.json").write_text(
        json.dumps({"version": "test", "families": families}, ensure_ascii=False),
        encoding="utf-8",
    )


def _published_rows(database: Database) -> list[tuple[str, str, str]]:
    with database.connect() as connection:
        return [
            (
                str(row["standard_key"]),
                str(row["current_version_id"]),
                str(row["snapshot_json"]),
            )
            for row in connection.execute(
                """
                SELECT standard.standard_key, standard.current_version_id,
                       version.snapshot_json
                FROM classification_standards standard
                JOIN classification_standard_versions version
                  ON version.id = standard.current_version_id
                ORDER BY standard.standard_key
                """
            ).fetchall()
        ]


def test_bootstrap_is_idempotent_and_seed_changes_do_not_overwrite(
    tmp_path: Path,
    monkeypatch,
) -> None:
    family = _family("gloves", "taxonomy_gloves.json")
    _write_seed(tmp_path, [family])
    monkeypatch.setattr(classification_standard_bootstrap, "PROJECT_ROOT", tmp_path)
    database = Database(tmp_path / "app.db")
    database.initialize()

    ClassificationStandardService(database)
    original_rows = _published_rows(database)
    _write_seed(tmp_path, [family], marker="后来修改的仓库规则")
    ClassificationStandardService(database)

    assert _published_rows(database) == original_rows


def test_bootstrap_adds_only_missing_seed_standard(
    tmp_path: Path,
    monkeypatch,
) -> None:
    gloves = _family("gloves", "taxonomy_gloves.json")
    footwear = _family("footwear", "taxonomy_footwear.json")
    _write_seed(tmp_path, [gloves])
    monkeypatch.setattr(classification_standard_bootstrap, "PROJECT_ROOT", tmp_path)
    database = Database(tmp_path / "app.db")
    database.initialize()

    ClassificationStandardService(database)
    original_gloves = _published_rows(database)
    _write_seed(tmp_path, [gloves, footwear])
    ClassificationStandardService(database)

    rows = _published_rows(database)
    assert [row[0] for row in rows] == ["footwear", "gloves"]
    assert next(row for row in rows if row[0] == "gloves") == original_gloves[0]
