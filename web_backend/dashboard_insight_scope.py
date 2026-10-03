"""洞察查询范围与连接内语义准备。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from web_backend.request_timing import timed_stage


@dataclass(frozen=True)
class InsightQueryScope:
    connection: sqlite3.Connection
    context: dict[str, Any]
    where_sql: str
    params: list[Any]
    option_where: str
    option_params: list[Any]
    unit_rollup: bool
    clean_group: str
    clean_subject: str
    requested_problem: str
    report_mode: bool
    records_table: str = "classification_result_records"


def subject_label_filter(scope: InsightQueryScope, record: str, label: str) -> str:
    if not scope.clean_subject:
        return ""
    return (
        " AND EXISTS (SELECT 1 FROM dashboard_insight_subject_labels subject_label"
        f" WHERE subject_label.result_version_id = {record}.result_version_id"
        f" AND subject_label.classification_key = {record}.classification_key"
        f" AND subject_label.label_code = {label}.label_code)"
    )


@timed_stage("insight_semantic_scope")
def prepare_scope_semantics(
    connection: sqlite3.Connection,
    where_sql: str,
    params: list[Any],
    *,
    records_table: str = "classification_result_records",
) -> None:
    """先准备基础范围的语义明细，当前连接内的对象子范围共用，权重另算。"""
    connection.execute(
        f"""
        CREATE TEMP TABLE IF NOT EXISTS dashboard_insight_scope_semantics AS
        WITH scoped_units AS MATERIALIZED (
            SELECT DISTINCT r.result_version_id, r.classification_key
            FROM {records_table} r WHERE {where_sql}
        )
        SELECT scoped_units.result_version_id, scoped_units.classification_key,
               unit.subject, unit.label_code
        FROM scoped_units
        JOIN classification_unit_semantics unit
          ON unit.result_version_id = scoped_units.result_version_id
         AND unit.classification_key = scoped_units.classification_key
        """,
        tuple(params),
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS temp.idx_insight_scope_semantics_unit "
        "ON dashboard_insight_scope_semantics(result_version_id, classification_key)"
    )
