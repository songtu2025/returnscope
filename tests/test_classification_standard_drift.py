from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path

from web_backend.classification_standard_drift import compare_published_standards


def _taxonomy(version: str, recognition_profile: str = "semantic_v1") -> dict:
    return {
        "version": version,
        "recognition_profile": recognition_profile,
        "agent_family": "测试智能体",
        "product_context": "测试商品",
        "allowed_parts": ["UNSPECIFIED"],
        "instructions": ["只依据原文判断。"],
        "labels": [
            {
                "code": "TEST_LABEL",
                "name": "测试标签",
                "description": "测试标签说明",
                "allowed_sentiments": ["NEGATIVE"],
            }
        ],
    }


def _family(key: str, taxonomy_file: str) -> dict:
    return {
        "key": key,
        "agent_family": "测试智能体",
        "logic_version": f"{key}-logic-v1",
        "taxonomy": taxonomy_file,
        "model_policy": {
            "version": f"{key}-policy-v1",
            "first_pass_role": "primary",
            "review_role": "secondary",
        },
        "variants": [
            {
                "category_a": "测试品类",
                "category_b": key,
                "attributes": {},
            }
        ],
    }


def _snapshot(family: dict, taxonomy: dict) -> dict:
    return {
        "standard_key": family["key"],
        "agent_family": family["agent_family"],
        "logic_version": family["logic_version"],
        "model_policy": family["model_policy"],
        "variants": family["variants"],
        "taxonomy": taxonomy,
    }


def _write_registry(
    root: Path,
    families: list[dict],
    taxonomies: dict[str, dict],
) -> Path:
    config_dir = root / "config"
    config_dir.mkdir()
    for file_name, taxonomy in taxonomies.items():
        (config_dir / file_name).write_text(
            json.dumps(taxonomy, ensure_ascii=False),
            encoding="utf-8",
        )
    registry_path = config_dir / "category_capabilities.json"
    registry_path.write_text(
        json.dumps({"version": "test", "families": families}, ensure_ascii=False),
        encoding="utf-8",
    )
    return registry_path


def _write_database(root: Path, snapshots: dict[str, dict]) -> Path:
    database_path = root / "app.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE classification_standards (
                id TEXT PRIMARY KEY,
                standard_key TEXT NOT NULL,
                status TEXT NOT NULL,
                current_version_id TEXT
            );
            CREATE TABLE classification_standard_versions (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                snapshot_json TEXT NOT NULL
            );
            """
        )
        for standard_key, snapshot in snapshots.items():
            standard_id = f"standard-{standard_key}"
            version_id = f"version-{standard_key}"
            connection.execute(
                """
                INSERT INTO classification_standards(
                    id, standard_key, status, current_version_id
                ) VALUES (?, ?, 'active', ?)
                """,
                (standard_id, standard_key, version_id),
            )
            connection.execute(
                """
                INSERT INTO classification_standard_versions(
                    id, status, snapshot_json
                ) VALUES (?, 'published', ?)
                """,
                (version_id, json.dumps(snapshot, ensure_ascii=False)),
            )
    return database_path


def test_matching_seed_and_published_standard(tmp_path: Path) -> None:
    family = _family("gloves", "taxonomy_gloves.json")
    taxonomy = _taxonomy("gloves-v1", "fact_v2")
    registry_path = _write_registry(
        tmp_path,
        [family],
        {"taxonomy_gloves.json": taxonomy},
    )
    database_path = _write_database(
        tmp_path,
        {"gloves": _snapshot(family, taxonomy)},
    )

    comparisons = compare_published_standards(database_path, registry_path)

    assert len(comparisons) == 1
    assert comparisons[0].status == "match"
    assert comparisons[0].differences == ()
    assert comparisons[0].seed_hash == comparisons[0].published_hash


def test_reports_execution_fields_that_drift(tmp_path: Path) -> None:
    family = _family("eyewear", "taxonomy_eyewear.json")
    seed_taxonomy = _taxonomy("eyewear-v1")
    published_taxonomy = deepcopy(seed_taxonomy)
    published_taxonomy["version"] = "eyewear-v2"
    published_taxonomy["recognition_profile"] = "fact_v2"
    published_taxonomy["labels"][0]["description"] = "已发布边界说明"
    published_snapshot = _snapshot(family, published_taxonomy)
    published_snapshot["model_policy"] = {
        **published_snapshot["model_policy"],
        "review_role": "primary",
    }
    registry_path = _write_registry(
        tmp_path,
        [family],
        {"taxonomy_eyewear.json": seed_taxonomy},
    )
    database_path = _write_database(
        tmp_path,
        {"eyewear": published_snapshot},
    )

    comparison = compare_published_standards(database_path, registry_path)[0]

    assert comparison.status == "drift"
    assert comparison.seed_recognition_profile == "semantic_v1"
    assert comparison.published_recognition_profile == "fact_v2"
    assert comparison.differences == (
        "model_policy",
        "taxonomy.version",
        "taxonomy.recognition_profile",
        "taxonomy.labels",
    )


def test_reports_standards_missing_from_either_side(tmp_path: Path) -> None:
    seed_family = _family("headwear", "taxonomy_headwear.json")
    published_family = _family("footwear", "taxonomy_footwear.json")
    seed_taxonomy = _taxonomy("headwear-v1")
    published_taxonomy = _taxonomy("footwear-v1")
    registry_path = _write_registry(
        tmp_path,
        [seed_family],
        {"taxonomy_headwear.json": seed_taxonomy},
    )
    database_path = _write_database(
        tmp_path,
        {"footwear": _snapshot(published_family, published_taxonomy)},
    )

    comparisons = compare_published_standards(database_path, registry_path)

    assert [(item.standard_key, item.status) for item in comparisons] == [
        ("footwear", "missing_seed"),
        ("headwear", "missing_published"),
    ]
