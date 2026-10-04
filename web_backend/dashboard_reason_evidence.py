from __future__ import annotations

import sqlite3
from typing import Any

from return_semantics.schemas import TaxonomyConfig
from web_backend.dashboard_insight_scope import (
    InsightQueryScope,
    subject_label_filter,
)
from web_backend.dashboard_support import serialize_record
from web_backend.request_timing import timed_stage

EVIDENCE_PAGE_SIZE = 10


@timed_stage("insight_evidence")
def list_reason_evidence(
    scope: InsightQueryScope,
    selected_code: str,
    taxonomy: TaxonomyConfig | None,
    *,
    page: int = 1,
    total: int | None = None,
) -> dict[str, Any]:
    connection = scope.connection
    query, params = _evidence_scope_query(scope, selected_code)
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
    _apply_problem_names(connection, items)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": EVIDENCE_PAGE_SIZE,
    }


def _evidence_scope_query(
    scope: InsightQueryScope, selected_code: str
) -> tuple[str, tuple[Any, ...]]:
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
                {subject_label_filter(scope, "r", "selected")}
                {group_condition}
          )
    """
    params = (*scope.params, selected_code)
    if scope.clean_group:
        params += (scope.clean_group,)
    return query, params


def _apply_problem_names(
    connection: sqlite3.Connection, items: list[dict[str, Any]]
) -> None:
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
