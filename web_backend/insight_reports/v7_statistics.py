from __future__ import annotations

from typing import Any

from web_backend.dashboard_insight_scope import InsightQueryScope
from web_backend.insight_report_profiles import PolarizationPair

# 用看板范围内的原始记录或反馈组代表行计数，每条记录对同一信号只贡献一次。
_SIGNAL_CTE = """
WITH scoped_units AS MATERIALIZED (
    SELECT result_version_id, classification_key, COUNT(*) AS weight
    FROM {records_table} r WHERE {where_sql}
    GROUP BY result_version_id, classification_key
), signals AS MATERIALIZED (
    SELECT s.result_version_id, s.classification_key,
           l.label_code AS code, l.label_name AS name,
           CASE l.label_kind WHEN 'positive' THEN 'positive' ELSE 'negative' END AS tone
    FROM scoped_units s
    JOIN classification_unit_labels l USING (result_version_id, classification_key)
    WHERE l.label_kind IN ('problem', 'positive')
    UNION ALL
    SELECT s.result_version_id, s.classification_key,
           json_extract(f.value, '$.label_code'), NULL,
           lower(json_extract(f.value, '$.sentiment'))
    FROM scoped_units s
    JOIN classification_units u USING (result_version_id, classification_key)
    JOIN json_each(u.classification_json, '$.semantic_units') f
    WHERE json_extract(f.value, '$.sentiment') IN ('POSITIVE', 'NEGATIVE', 'NEUTRAL')
), per_label AS (
    SELECT result_version_id, classification_key, code, MAX(name) AS name,
           MAX(tone = 'positive') AS positive, MAX(tone = 'negative') AS negative
    FROM signals GROUP BY result_version_id, classification_key, code
), per_unit AS (
    SELECT result_version_id, classification_key,
           MAX(positive) AS positive, MAX(negative) AS negative,
           MAX(code IS NOT NULL AND code <> '') AS labeled
    FROM per_label GROUP BY result_version_id, classification_key
)
"""


def collect_report_signals(
    scope: InsightQueryScope, pairs: tuple[PolarizationPair, ...] = ()
) -> dict[str, Any]:
    sql = _SIGNAL_CTE.format(
        records_table=scope.records_table, where_sql=scope.where_sql
    )
    rows = scope.connection.execute(
        sql
        + """
        SELECT code, MAX(name) AS label,
               SUM(weight * positive) AS positive, SUM(weight * negative) AS negative,
               SUM(weight * (positive OR negative)) AS matched
        FROM per_label JOIN scoped_units USING (result_version_id, classification_key)
        WHERE code IS NOT NULL AND code <> ''
        GROUP BY code ORDER BY code
        """,
        scope.params,
    ).fetchall()
    overview = scope.connection.execute(
        sql
        + """
        SELECT COALESCE(SUM(CASE WHEN positive AND negative THEN weight ELSE 0 END), 0)
                   AS mixed,
               COALESCE(SUM(CASE WHEN positive AND NOT negative THEN weight ELSE 0 END), 0)
                   AS positive,
               COALESCE(SUM(CASE WHEN negative AND NOT positive THEN weight ELSE 0 END), 0)
                   AS negative,
               COALESCE(SUM(CASE WHEN positive OR negative THEN 0 ELSE weight END), 0)
                   AS unclear,
               COALESCE(SUM(weight * labeled), 0) AS labeled,
               COALESCE(SUM(weight), 0) AS total
        FROM scoped_units LEFT JOIN per_unit USING (result_version_id, classification_key)
        """,
        scope.params,
    ).fetchone()
    return {
        "labels": [dict(row) for row in rows],
        "overview": dict(overview),
        "paired_labels": _collect_paired_signals(scope, sql, pairs),
    }


def _collect_paired_signals(
    scope: InsightQueryScope, sql: str, pairs: tuple[PolarizationPair, ...]
) -> list[dict[str, Any]]:
    if not pairs:
        return []
    aliases = [
        (index, side, code)
        for index, pair in enumerate(pairs)
        for side, codes in enumerate(pair)
        for code in codes
    ]
    placeholders = ", ".join(["(?, ?, ?)"] * len(aliases))
    # 先将同方向的现行和历史编码合并，再以相同看板权重计算联合与重叠。
    rows = scope.connection.execute(
        sql
        + f"""
        , pair_aliases(pair_index, side, code) AS (VALUES {placeholders}),
        paired_units AS (
            SELECT result_version_id, classification_key, pair_index,
                   MAX(side = 0) AS left_hit, MAX(side = 1) AS right_hit
            FROM per_label JOIN pair_aliases USING (code)
            WHERE positive OR negative
            GROUP BY result_version_id, classification_key, pair_index
        )
        SELECT pair_index, SUM(weight * left_hit) AS left_count,
               SUM(weight * right_hit) AS right_count,
               SUM(weight * (left_hit AND right_hit)) AS overlap,
               SUM(weight) AS union_count
        FROM paired_units JOIN scoped_units USING (result_version_id, classification_key)
        GROUP BY pair_index ORDER BY pair_index
        """,
        (*scope.params, *(value for alias in aliases for value in alias)),
    )
    return [
        {
            "directions": [list(codes) for codes in pairs[row["pair_index"]]],
            "left_count": row["left_count"],
            "right_count": row["right_count"],
            "overlap": row["overlap"],
            "union_count": row["union_count"],
        }
        for row in rows
    ]
