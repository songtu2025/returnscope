from __future__ import annotations

import sqlite3
from typing import Any

from web_backend.dashboard_support import percentage

_TREND_SQL = """
    SELECT date(
               r.return_date,
               '-' || ((CAST(strftime('%w', r.return_date) AS INTEGER)
               + 6) % 7) || ' days'
           ) AS period_start,
           date(
               r.return_date,
               '-' || ((CAST(strftime('%w', r.return_date) AS INTEGER)
               + 6) % 7) || ' days',
               '+6 days'
           ) AS period_end,
           COUNT(*) AS total_record_count,
           SUM(CASE WHEN EXISTS (
               SELECT 1 FROM classification_unit_labels selected
               WHERE selected.result_version_id = r.result_version_id
                 AND selected.classification_key = r.classification_key
                 AND selected.label_kind = 'problem'
                 AND selected.label_code = ?
           ) THEN 1 ELSE 0 END) AS record_count
    FROM classification_result_records r
    WHERE {case_where} AND r.return_date IS NOT NULL
    GROUP BY period_start, period_end
    ORDER BY period_start
"""

_CO_REASONS_SQL = """
    SELECT other.label_code AS value,
           COALESCE(NULLIF(TRIM(other.label_name), ''),
                    other.label_code) AS label,
           COUNT(DISTINCT r.id) AS record_count
    FROM classification_result_records r
    JOIN classification_unit_labels selected
      ON selected.result_version_id = r.result_version_id
     AND selected.classification_key = r.classification_key
     AND selected.label_kind = 'problem'
     AND selected.label_code = ?
    JOIN classification_unit_labels other
      ON other.result_version_id = r.result_version_id
     AND other.classification_key = r.classification_key
     AND other.label_kind = 'problem'
     AND other.label_code <> ?
    WHERE {case_where}
    GROUP BY other.label_code, other.label_name
    ORDER BY record_count DESC, label COLLATE NOCASE ASC
    LIMIT 6
"""


def collect_case_trend(
    connection: sqlite3.Connection,
    code: str,
    case_where: str,
    case_params: tuple[Any, ...],
) -> list[dict[str, Any]]:
    trend_rows = connection.execute(
        _TREND_SQL.format(case_where=case_where),
        (code, *case_params),
    ).fetchall()
    return [
        {
            "period_start": row["period_start"],
            "period_end": row["period_end"],
            "record_count": int(row["record_count"] or 0),
            "total_record_count": int(row["total_record_count"] or 0),
            "percentage": percentage(
                int(row["record_count"] or 0),
                int(row["total_record_count"] or 0),
            ),
            "low_sample": int(row["total_record_count"] or 0) < 10,
        }
        for row in trend_rows
    ]


def collect_case_co_reasons(
    connection: sqlite3.Connection,
    case: dict[str, Any],
    code: str,
    case_where: str,
    case_params: tuple[Any, ...],
) -> list[dict[str, Any]]:
    co_reason_rows = connection.execute(
        _CO_REASONS_SQL.format(case_where=case_where),
        (code, code, *case_params),
    ).fetchall()
    return [
        {
            "value": str(row["value"]),
            "label": str(row["label"]),
            "record_count": int(row["record_count"]),
            "percentage": percentage(
                int(row["record_count"]),
                int(case["record_count"]),
            ),
        }
        for row in co_reason_rows
    ]
