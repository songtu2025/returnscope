from __future__ import annotations

from typing import Any, cast

from return_semantics.schemas import TaxonomyConfig
from web_backend.dashboard_insight_overview import InsightQueryScope
from web_backend.dashboard_support import percentage, serialize_record

EVIDENCE_PAGE_SIZE = 10


def list_reason_evidence(
    scope: InsightQueryScope,
    selected_code: str,
    taxonomy: TaxonomyConfig | None,
    *,
    page: int = 1,
    total: int | None = None,
) -> dict[str, Any]:
    connection = scope.connection
    source = (
        "classification_result_records r"
        if scope.records_table == "classification_result_records"
        else (
            f"{scope.records_table} scoped "
            "JOIN classification_result_records r ON r.id = scoped.id"
        )
    )
    group_condition = (
        "AND aligned_group(selected.label_group, selected.label_code, "
        "r.result_version_id) = ?"
        if scope.clean_group
        else ""
    )
    query = f"""
        FROM {source}
        JOIN classification_units u
          ON u.result_version_id = r.result_version_id
         AND u.classification_key = r.classification_key
        WHERE {scope.where_sql}
          AND EXISTS (
              SELECT 1 FROM classification_unit_labels selected
              WHERE selected.result_version_id = r.result_version_id
                AND selected.classification_key = r.classification_key
                AND selected.label_kind = 'problem'
                AND selected.label_code = ?
                {group_condition}
          )
    """
    params = (*scope.params, selected_code)
    if scope.clean_group:
        params += (scope.clean_group,)
    if total is None:
        total = int(
            connection.execute(f"SELECT COUNT(*) {query}", params).fetchone()[0]
        )
    rows = connection.execute(
        f"""
        SELECT r.*, u.processing_status, u.problem_labels_json,
               u.classification_json
        {query}
        ORDER BY datetime(r.return_date) DESC,
                 r.source_row DESC, r.id ASC
        LIMIT ? OFFSET ?
        """,
        (*params, EVIDENCE_PAGE_SIZE, (page - 1) * EVIDENCE_PAGE_SIZE),
    ).fetchall()
    items = [serialize_record(dict(row), taxonomy) for row in rows]
    label_names: dict[str, str] = {}
    if items:
        placeholders = ",".join("?" for _ in items)
        names = connection.execute(
            f"""
            SELECT DISTINCT l.label_code, l.label_name
            FROM classification_unit_labels l
            JOIN classification_result_records r
              ON r.result_version_id = l.result_version_id
             AND r.classification_key = l.classification_key
            WHERE r.id IN ({placeholders}) AND l.label_kind = 'problem'
            ORDER BY l.label_code, l.label_name
            """,
            tuple(item["id"] for item in items),
        ).fetchall()
        label_names = {
            str(row["label_code"]): str(row["label_name"] or row["label_code"])
            for row in names
        }
    for item in items:
        item["problem_labels"] = [
            label_names.get(str(label), str(label)) for label in item["problem_labels"]
        ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": EVIDENCE_PAGE_SIZE,
    }


def collect_reason_details(
    scope: InsightQueryScope,
    selected_reason: dict[str, Any] | None,
    overview: dict[str, Any],
    taxonomy: TaxonomyConfig | None = None,
) -> dict[str, Any]:
    connection = scope.connection
    where_sql = scope.where_sql
    params = scope.params
    total_records = int(overview["total_records"])
    label_counts = cast(dict[str, int], overview["label_counts"])

    trend: list[dict[str, Any]] = []
    products: list[dict[str, Any]] = []
    variants: list[dict[str, Any]] = []
    co_reasons: list[dict[str, Any]] = []
    semantic_parts: list[dict[str, Any]] = []
    semantic_opinions: list[dict[str, Any]] = []
    semantic_record_count = 0
    evidence_items: list[dict[str, Any]] = []
    evidence_total = 0
    if selected_reason:
        selected_code = str(selected_reason["value"])
        connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS dashboard_insight_selected_records "
            "(id TEXT PRIMARY KEY)"
        )
        connection.execute("DELETE FROM dashboard_insight_selected_records")
        connection.execute(
            f"""
            INSERT INTO dashboard_insight_selected_records(id)
            SELECT DISTINCT r.id
            FROM {scope.records_table} r
            JOIN classification_unit_labels selected
              ON selected.result_version_id = r.result_version_id
             AND selected.classification_key = r.classification_key
             AND selected.label_kind = 'problem'
             AND selected.label_code = ?
            WHERE {where_sql}
            """,
            (selected_code, *params),
        )
        trend_rows = connection.execute(
            f"""
            SELECT date(r.return_date, 'weekday 0', '-6 days') AS period_start,
                   date(r.return_date, 'weekday 0') AS period_end,
                   COUNT(r.id) AS total_record_count,
                   SUM(CASE WHEN matched.id IS NOT NULL
                            THEN 1 ELSE 0 END) AS record_count
            FROM {scope.records_table} r
            LEFT JOIN dashboard_insight_selected_records matched
              ON matched.id = r.id
            WHERE {where_sql} AND r.return_date IS NOT NULL
            GROUP BY period_start, period_end
            ORDER BY period_start
            """,
            tuple(params),
        ).fetchall()
        trend = [
            {
                **dict(row),
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
        product_rows = connection.execute(
            f"""
            SELECT COALESCE(NULLIF(TRIM(r.product_name), ''), '未提供产品')
                       AS value,
                   COUNT(r.id) AS total_record_count,
                   SUM(CASE WHEN matched.id IS NOT NULL
                            THEN 1 ELSE 0 END) AS record_count
            FROM {scope.records_table} r
            LEFT JOIN dashboard_insight_selected_records matched
              ON matched.id = r.id
            WHERE {where_sql}
            GROUP BY value
            HAVING record_count > 0
            ORDER BY record_count DESC, value COLLATE NOCASE ASC
            LIMIT 8
            """,
            tuple(params),
        ).fetchall()
        selected_count = int(selected_reason["record_count"])
        products = [
            {
                "value": row["value"],
                "record_count": int(row["record_count"]),
                "total_record_count": int(row["total_record_count"]),
                "reason_share": percentage(int(row["record_count"]), selected_count),
                "product_reason_rate": percentage(
                    int(row["record_count"]),
                    int(row["total_record_count"]),
                ),
                "overall_reason_rate": percentage(selected_count, total_records),
                "lift": round(
                    (int(row["record_count"]) / int(row["total_record_count"]))
                    / (selected_count / total_records),
                    2,
                )
                if total_records and selected_count
                else 0.0,
                "reliable": int(row["total_record_count"]) >= 15,
            }
            for row in product_rows
        ]
        variant_rows = connection.execute(
            f"""
            SELECT COALESCE(NULLIF(TRIM(r.product_sku), ''), '未提供 SKU')
                       AS value,
                   COALESCE(NULLIF(TRIM(r.product_name), ''), '未提供产品')
                       AS product_name,
                   COUNT(r.id) AS total_record_count,
                   SUM(CASE WHEN matched.id IS NOT NULL
                            THEN 1 ELSE 0 END) AS record_count
            FROM {scope.records_table} r
            LEFT JOIN dashboard_insight_selected_records matched
              ON matched.id = r.id
            WHERE {where_sql}
            GROUP BY value, product_name
            HAVING record_count > 0
            ORDER BY record_count DESC, value COLLATE NOCASE ASC
            LIMIT 12
            """,
            tuple(params),
        ).fetchall()
        variants = [
            {
                "value": str(row["value"]),
                "product_name": str(row["product_name"]),
                "record_count": int(row["record_count"]),
                "total_record_count": int(row["total_record_count"]),
                "reason_share": percentage(int(row["record_count"]), selected_count),
                "product_reason_rate": percentage(
                    int(row["record_count"]),
                    int(row["total_record_count"]),
                ),
                "overall_reason_rate": percentage(selected_count, total_records),
                "lift": round(
                    (int(row["record_count"]) / int(row["total_record_count"]))
                    / (selected_count / total_records),
                    2,
                )
                if total_records and selected_count
                else 0.0,
                "reliable": int(row["total_record_count"]) >= 10,
            }
            for row in variant_rows
        ]
        co_reason_rows = connection.execute(
            f"""
            SELECT other.label_code AS value,
                   COALESCE(NULLIF(TRIM(other.label_name), ''),
                            other.label_code) AS label,
                   COUNT(r.id) AS record_count
            FROM {scope.records_table} r
            JOIN dashboard_insight_selected_records selected
              ON selected.id = r.id
            JOIN classification_unit_labels other
              ON other.result_version_id = r.result_version_id
             AND other.classification_key = r.classification_key
             AND other.label_kind = 'problem'
             AND other.label_code <> ?
            WHERE {where_sql}
            GROUP BY other.label_code, other.label_name
            ORDER BY record_count DESC, label COLLATE NOCASE ASC
            LIMIT 6
            """,
            (selected_code, *params),
        ).fetchall()
        co_reasons = [
            {
                **dict(row),
                "record_count": int(row["record_count"]),
                "percentage": percentage(int(row["record_count"]), selected_count),
                "lift": round(
                    (int(row["record_count"]) / selected_count)
                    / (label_counts.get(str(row["value"]), 0) / total_records),
                    2,
                )
                if total_records and label_counts.get(str(row["value"]), 0)
                else 0.0,
            }
            for row in co_reason_rows
        ]
        semantic_rows = connection.execute(
            f"""
            WITH matched AS MATERIALIZED (
                SELECT r.id AS record_id,
                       COALESCE(
                           NULLIF(json_extract(unit.value, '$.part'), ''),
                           'UNSPECIFIED'
                       ) AS part,
                       json_extract(unit.value, '$.opinion') AS opinion,
                       json_extract(unit.value, '$.subject') AS subject,
                       json_extract(unit.value, '$.evidence') AS evidence
                FROM {scope.records_table} r
                JOIN classification_units u
                  ON u.result_version_id = r.result_version_id
                 AND u.classification_key = r.classification_key
                JOIN dashboard_insight_selected_records selected
                  ON selected.id = r.id
                JOIN json_each(u.classification_json, '$.semantic_units') unit
                WHERE {where_sql}
                  AND json_extract(unit.value, '$.label_code') = ?
            ),
            part_counts AS (
                SELECT part AS value, COUNT(DISTINCT record_id) AS record_count
                FROM matched
                GROUP BY part
                ORDER BY record_count DESC, value ASC
                LIMIT 6
            ),
            opinion_counts AS (
                SELECT opinion, subject, part,
                       COUNT(DISTINCT record_id) AS record_count,
                       MAX(evidence) AS evidence
                FROM matched
                WHERE NULLIF(opinion, '') IS NOT NULL
                GROUP BY opinion, subject, part
                ORDER BY record_count DESC, opinion ASC
                LIMIT 4
            )
            SELECT 'total' AS kind, NULL AS value, NULL AS subject,
                   NULL AS part, COUNT(DISTINCT record_id) AS record_count,
                   NULL AS evidence
            FROM matched
            UNION ALL
            SELECT 'part', value, NULL, NULL, record_count, NULL
            FROM part_counts
            UNION ALL
            SELECT 'opinion', opinion, subject, part, record_count, evidence
            FROM opinion_counts
            """,
            (*params, selected_code),
        ).fetchall()
        semantic_record_count = int(semantic_rows[0]["record_count"])
        part_rows = sorted(
            (row for row in semantic_rows if row["kind"] == "part"),
            key=lambda row: (-int(row["record_count"]), str(row["value"])),
        )
        semantic_parts = [
            {
                "value": str(row["value"]),
                "record_count": int(row["record_count"]),
                "percentage": percentage(
                    int(row["record_count"]), semantic_record_count
                ),
            }
            for row in part_rows
        ]
        opinion_rows = sorted(
            (row for row in semantic_rows if row["kind"] == "opinion"),
            key=lambda row: (-int(row["record_count"]), str(row["value"])),
        )
        semantic_opinions = [
            {
                "opinion": row["value"],
                "subject": row["subject"],
                "part": row["part"],
                "record_count": int(row["record_count"]),
                "evidence": row["evidence"],
            }
            for row in opinion_rows
        ]
        evidence_total = selected_count
        evidence_items = list_reason_evidence(
            scope,
            selected_code,
            taxonomy,
            total=evidence_total,
        )["items"]

    return {
        "trend": trend,
        "products": products,
        "variants": variants,
        "co_reasons": co_reasons,
        "semantic_parts": semantic_parts,
        "semantic_opinions": semantic_opinions,
        "semantic_record_count": semantic_record_count,
        "evidence_items": evidence_items,
        "evidence_total": evidence_total,
    }
