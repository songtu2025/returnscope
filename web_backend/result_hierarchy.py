from __future__ import annotations

import json
import sqlite3
from typing import Any

from return_semantics.schemas import TaxonomyConfig
from return_semantics.taxonomy_hierarchy import label_path, label_path_codes


def result_taxonomy(
    connection: sqlite3.Connection, version_id: str
) -> TaxonomyConfig | None:
    """只读取结果绑定的标准快照，历史缺失关系时不借用当前标准。"""
    row = connection.execute(
        """
        SELECT s.snapshot_json FROM classification_result_versions v
        JOIN classification_results r ON r.id = v.result_id
        JOIN classification_standard_versions s ON s.id = r.standard_version_id
        WHERE v.id = ?
        """,
        (version_id,),
    ).fetchone()
    return (
        TaxonomyConfig.model_validate(json.loads(row[0])["taxonomy"]) if row else None
    )


def enrich_record(
    item: dict[str, Any], taxonomy: TaxonomyConfig | None
) -> dict[str, Any]:
    """在响应中派生路径，不改写持久化历史结果。"""
    if taxonomy is None:
        return item
    classification = item.get("classification", {})
    codes = set(item.get("problem_labels", []))
    codes.update(classification.get("problem_label_codes", []))
    codes.update(classification.get("primary_label_codes", []))
    codes.update(classification.get("positive_label_codes", []))
    item["problem_label_paths"] = {
        code: label_path(taxonomy, code) for code in sorted(codes)
    }
    for unit in classification.get("semantic_units", []):
        unit["label_path"] = label_path(taxonomy, unit["label_code"])
    return item


def hierarchy_counts(
    connection: sqlite3.Connection,
    taxonomy: TaxonomyConfig,
    where_sql: str,
    params: list[Any],
) -> list[dict[str, Any]]:
    """父级统计合并原始记录集合，不累加兄弟标签或整组权重。"""
    nodes = {node.code: node for node in [*taxonomy.categories, *taxonomy.labels]}
    records: dict[str, set[str]] = {}
    units: dict[str, set[str]] = {}
    rows = connection.execute(
        f"""
        SELECT r.id, r.result_version_id, r.classification_key, l.label_code
        FROM classification_result_records r
        JOIN classification_unit_labels l
          ON l.result_version_id = r.result_version_id
         AND l.classification_key = r.classification_key
         AND l.label_kind = 'problem'
        WHERE {where_sql}
        """,
        tuple(params),
    )
    for row in rows:
        for code in label_path_codes(taxonomy, row["label_code"]):
            records.setdefault(code, set()).add(row["id"])
            units.setdefault(code, set()).add(
                f"{row['result_version_id']}:{row['classification_key']}"
            )
    return sorted(
        [
            {
                "value": code,
                "label_code": code,
                "label_name": nodes[code].name,
                "label_path": label_path(taxonomy, code),
                "parent_code": nodes[code].parent_code,
                "record_count": len(ids),
                "unit_count": len(units[code]),
            }
            for code, ids in records.items()
        ],
        key=lambda item: (-item["record_count"], item["value"]),
    )
