from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from return_semantics.schemas import TaxonomyConfig

ComparisonStatus = Literal[
    "match",
    "drift",
    "missing_seed",
    "missing_published",
]

_TAXONOMY_FIELDS = (
    "version",
    "structure_version",
    "recognition_profile",
    "agent_family",
    "product_context",
    "allowed_parts",
    "instructions",
    "validation_rules",
    "categories",
    "labels",
)


@dataclass(frozen=True)
class StandardDriftComparison:
    standard_key: str
    status: ComparisonStatus
    seed_taxonomy_version: str | None
    published_taxonomy_version: str | None
    seed_recognition_profile: str | None
    published_recognition_profile: str | None
    seed_hash: str | None
    published_hash: str | None
    published_version_id: str | None
    differences: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare_published_standards(
    database_path: Path,
    registry_path: Path,
) -> list[StandardDriftComparison]:
    """只读比较仓库初始化配置与数据库当前已发布标准。"""
    seed_snapshots = _load_seed_snapshots(registry_path)
    published_snapshots = _load_published_snapshots(database_path)
    comparisons = []
    for standard_key in sorted(seed_snapshots.keys() | published_snapshots.keys()):
        seed = seed_snapshots.get(standard_key)
        published = published_snapshots.get(standard_key)
        comparisons.append(_compare_standard(standard_key, seed, published))
    return comparisons


def _load_seed_snapshots(registry_path: Path) -> dict[str, dict[str, Any]]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    snapshots = {}
    for family in registry["families"]:
        standard_key = str(family["key"])
        taxonomy_path = registry_path.parent / str(family["taxonomy"])
        snapshots[standard_key] = {
            "standard_key": standard_key,
            "agent_family": family["agent_family"],
            "logic_version": family["logic_version"],
            "model_policy": family["model_policy"],
            "variants": family["variants"],
            "taxonomy": json.loads(taxonomy_path.read_text(encoding="utf-8")),
        }
    return snapshots


def _load_published_snapshots(
    database_path: Path,
) -> dict[str, dict[str, Any]]:
    if not database_path.is_file():
        raise FileNotFoundError(f"数据库不存在：{database_path}")
    database_uri = f"{database_path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(database_uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT s.standard_key, v.id AS published_version_id, v.snapshot_json
            FROM classification_standards s
            JOIN classification_standard_versions v
              ON v.id = s.current_version_id
            WHERE s.status = 'active' AND v.status = 'published'
            ORDER BY s.standard_key
            """
        ).fetchall()
    snapshots = {}
    for row in rows:
        snapshot = json.loads(row["snapshot_json"])
        snapshot["published_version_id"] = str(row["published_version_id"])
        snapshots[str(row["standard_key"])] = snapshot
    return snapshots


def _compare_standard(
    standard_key: str,
    seed: dict[str, Any] | None,
    published: dict[str, Any] | None,
) -> StandardDriftComparison:
    if seed is None:
        return _missing_comparison(
            standard_key,
            "missing_seed",
            published=published,
        )
    if published is None:
        return _missing_comparison(
            standard_key,
            "missing_published",
            seed=seed,
        )

    canonical_seed = _canonical_execution_snapshot(seed)
    canonical_published = _canonical_execution_snapshot(published)
    differences = _execution_differences(canonical_seed, canonical_published)
    return StandardDriftComparison(
        standard_key=standard_key,
        status="drift" if differences else "match",
        seed_taxonomy_version=canonical_seed["taxonomy"]["version"],
        published_taxonomy_version=canonical_published["taxonomy"]["version"],
        seed_recognition_profile=canonical_seed["taxonomy"]["recognition_profile"],
        published_recognition_profile=canonical_published["taxonomy"][
            "recognition_profile"
        ],
        seed_hash=_content_hash(canonical_seed),
        published_hash=_content_hash(canonical_published),
        published_version_id=str(published["published_version_id"]),
        differences=tuple(differences),
    )


def _missing_comparison(
    standard_key: str,
    status: Literal["missing_seed", "missing_published"],
    *,
    seed: dict[str, Any] | None = None,
    published: dict[str, Any] | None = None,
) -> StandardDriftComparison:
    canonical_seed = _canonical_execution_snapshot(seed) if seed else None
    canonical_published = (
        _canonical_execution_snapshot(published) if published else None
    )
    return StandardDriftComparison(
        standard_key=standard_key,
        status=status,
        seed_taxonomy_version=(
            canonical_seed["taxonomy"]["version"] if canonical_seed else None
        ),
        published_taxonomy_version=(
            canonical_published["taxonomy"]["version"] if canonical_published else None
        ),
        seed_recognition_profile=(
            canonical_seed["taxonomy"]["recognition_profile"]
            if canonical_seed
            else None
        ),
        published_recognition_profile=(
            canonical_published["taxonomy"]["recognition_profile"]
            if canonical_published
            else None
        ),
        seed_hash=_content_hash(canonical_seed) if canonical_seed else None,
        published_hash=(
            _content_hash(canonical_published) if canonical_published else None
        ),
        published_version_id=(
            str(published["published_version_id"]) if published else None
        ),
        differences=(status,),
    )


def _canonical_execution_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    taxonomy = TaxonomyConfig.model_validate(snapshot["taxonomy"]).model_dump(
        mode="json"
    )
    policy = snapshot["model_policy"]
    variants = [
        {
            "category_a": str(variant["category_a"]).strip(),
            "category_b": str(variant["category_b"]).strip(),
            "attributes": {
                str(key): str(value)
                for key, value in variant.get("attributes", {}).items()
            },
        }
        for variant in snapshot["variants"]
    ]
    return {
        "agent_family": str(snapshot["agent_family"]),
        "logic_version": str(snapshot["logic_version"]),
        "model_policy": {
            "version": str(policy["version"]),
            "first_pass_role": str(policy["first_pass_role"]),
            "review_role": (
                str(policy["review_role"]) if policy.get("review_role") else None
            ),
        },
        "variants": variants,
        "taxonomy": taxonomy,
    }


def _execution_differences(
    seed: dict[str, Any],
    published: dict[str, Any],
) -> list[str]:
    differences = []
    for field_name in ("agent_family", "logic_version", "model_policy", "variants"):
        if seed[field_name] != published[field_name]:
            differences.append(field_name)
    for field_name in _TAXONOMY_FIELDS:
        if seed["taxonomy"][field_name] != published["taxonomy"][field_name]:
            differences.append(f"taxonomy.{field_name}")
    return differences


def _content_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
