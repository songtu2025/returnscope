"""查询反馈组分页并组装源明细，复用既有反馈分组规则。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from web_backend.result_hierarchy import feedback_group_key_sql

GROUP_MEMBERS_SQL = """
    , selected AS (
        SELECT display_key, first_row, member_count
        FROM grouped
        ORDER BY first_row, display_key
        LIMIT ? OFFSET ?
    )
    SELECT f.*, s.member_count, u.processing_status,
           u.problem_labels_json, u.classification_json, u.system_rerun_required
    FROM filtered f
    JOIN selected s ON s.display_key = f.display_key
    JOIN classification_units u
      ON u.result_version_id = f.result_version_id
     AND u.classification_key = f.classification_key
    ORDER BY s.first_row, f.source_row, f.id
    """


def fetch_record_group_page(
    connection: Any,
    filters: tuple[str, list[Any]],
    page: int,
    page_size: int,
) -> tuple[Any, list[Any]]:
    where_sql, params = filters
    group_key = feedback_group_key_sql("r")
    grouped_sql = f"""
        WITH filtered AS (
            SELECT r.*, {group_key} AS display_key
            FROM classification_result_records r
            WHERE {where_sql}
        ), grouped AS (
            SELECT display_key, MIN(source_row) AS first_row,
                   COUNT(*) AS member_count
            FROM filtered GROUP BY display_key
        )
    """
    totals = connection.execute(
        grouped_sql + "SELECT COUNT(*) AS groups, "
        "COALESCE(SUM(member_count), 0) AS sources FROM grouped",
        tuple(params),
    ).fetchone()
    rows = connection.execute(
        grouped_sql + GROUP_MEMBERS_SQL,
        (*params, page_size, (page - 1) * page_size),
    ).fetchall()
    return totals, rows


def assemble_record_groups(
    rows: list[Any],
    prepare_record: Callable[[dict[str, Any]], dict[str, Any]],
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = dict(row)
        key = str(value.pop("display_key"))
        member_count = int(value.pop("member_count"))
        member = {
            name: value[name]
            for name in (
                "source_record_id",
                "source_row",
                "source_origin_id",
                "return_date",
                "reason",
                "comment",
            )
        }
        group = by_key.get(key)
        if group is None:
            group = {
                "record": prepare_record(value),
                "member_count": member_count,
                "members": [],
            }
            by_key[key] = group
            groups.append(group)
        group["members"].append(member)
    return groups
