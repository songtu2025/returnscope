from __future__ import annotations

import sqlite3
from typing import Any

from web_backend.dashboard_support import percentage

_COVERAGE_SQL = """
    SELECT COUNT(DISTINCT r.id) AS record_count,
           COUNT(DISTINCT CASE
               WHEN UPPER(COALESCE(
                   NULLIF(json_extract(unit.value, '$.part'), ''),
                   'UNSPECIFIED'
               )) <> 'UNSPECIFIED'
               THEN r.id
           END) AS specified_part_record_count
    FROM classification_result_records r
    JOIN classification_units u
      ON u.result_version_id = r.result_version_id
     AND u.classification_key = r.classification_key
    JOIN json_each(u.classification_json, '$.semantic_units') unit
    WHERE {case_where}
      AND json_extract(unit.value, '$.label_code') = ?
"""

_PARTS_SQL = """
    SELECT COALESCE(
               NULLIF(json_extract(unit.value, '$.part'), ''),
               'UNSPECIFIED'
           ) AS value,
           COUNT(DISTINCT r.id) AS record_count
    FROM classification_result_records r
    JOIN classification_units u
      ON u.result_version_id = r.result_version_id
     AND u.classification_key = r.classification_key
    JOIN json_each(u.classification_json, '$.semantic_units') unit
    WHERE {case_where}
      AND json_extract(unit.value, '$.label_code') = ?
    GROUP BY value
    ORDER BY record_count DESC, value ASC
    LIMIT 6
"""

_OPINIONS_SQL = """
    SELECT json_extract(unit.value, '$.opinion') AS opinion,
           json_extract(unit.value, '$.subject') AS subject,
           COALESCE(
               NULLIF(json_extract(unit.value, '$.part'), ''),
               'UNSPECIFIED'
           ) AS part,
           COUNT(DISTINCT r.id) AS record_count,
           MIN(json_extract(unit.value, '$.evidence')) AS evidence
    FROM classification_result_records r
    JOIN classification_units u
      ON u.result_version_id = r.result_version_id
     AND u.classification_key = r.classification_key
    JOIN json_each(u.classification_json, '$.semantic_units') unit
    WHERE {case_where}
      AND json_extract(unit.value, '$.label_code') = ?
      AND NULLIF(json_extract(unit.value, '$.opinion'), '') IS NOT NULL
    GROUP BY opinion, subject, part
    ORDER BY record_count DESC, opinion ASC
    LIMIT 6
"""


def _semantic_parts(
    part_rows: list[sqlite3.Row], semantic_count: int
) -> list[dict[str, Any]]:
    return [
        {
            "value": str(row["value"]),
            "record_count": int(row["record_count"]),
            "percentage": percentage(
                int(row["record_count"]),
                semantic_count,
            ),
        }
        for row in part_rows
    ]


def _semantic_opinions(opinion_rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [
        {
            "opinion": str(row["opinion"]),
            "subject": row["subject"],
            "part": str(row["part"]),
            "record_count": int(row["record_count"]),
            "evidence": row["evidence"],
        }
        for row in opinion_rows
    ]


def collect_case_semantics(
    connection: sqlite3.Connection,
    case: dict[str, Any],
    code: str,
    case_where: str,
    case_params: tuple[Any, ...],
) -> dict[str, Any]:
    semantic_row = connection.execute(
        _COVERAGE_SQL.format(case_where=case_where),
        (*case_params, code),
    ).fetchone()
    semantic_count = int(semantic_row["record_count"] or 0)
    specified_count = int(semantic_row["specified_part_record_count"] or 0)
    part_rows = connection.execute(
        _PARTS_SQL.format(case_where=case_where),
        (*case_params, code),
    ).fetchall()
    opinion_rows = connection.execute(
        _OPINIONS_SQL.format(case_where=case_where),
        (*case_params, code),
    ).fetchall()
    return {
        "record_count": semantic_count,
        "coverage": percentage(
            semantic_count,
            int(case["record_count"]),
        ),
        "specified_part_record_count": specified_count,
        "specified_part_coverage": percentage(
            specified_count,
            semantic_count,
        ),
        "parts": _semantic_parts(part_rows, semantic_count),
        "opinions": _semantic_opinions(opinion_rows),
    }
