from __future__ import annotations

import builtins
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from web_backend.common import json_value
from web_backend.database import Database
from web_backend.operations.audit_targets import (
    _target,
    _target_context,
)

_AUDIT_ROWS_SQL = """
                SELECT a.*, u.display_name AS actor_name
                FROM audit_logs a
                LEFT JOIN users u ON u.id = a.actor_id
                WHERE {where_sql}
                ORDER BY a.created_at DESC, a.id ASC
                LIMIT ? OFFSET ?
                """


class AuditLogService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list(
        self,
        *,
        actor_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        action: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        where_sql, params = self._query_filters(
            (
                ("a.actor_id", actor_id),
                ("a.entity_type", entity_type),
                ("a.entity_id", entity_id),
                ("a.action", action),
            ),
            date_from,
            date_to,
        )
        with self.database.connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM audit_logs a WHERE {where_sql}",
                    tuple(params),
                ).fetchone()[0]
            )
            rows = connection.execute(
                _AUDIT_ROWS_SQL.format(where_sql=where_sql),
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
            target_context = self._target_context(connection, rows)
        items = self._serialize_rows(rows, target_context)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _query_filters(
        self,
        filters: tuple[tuple[str, str | None], ...],
        date_from: str | None,
        date_to: str | None,
    ) -> tuple[str, builtins.list[Any]]:
        where = ["1 = 1"]
        params: list[Any] = []
        for column, value in filters:
            if value:
                where.append(f"{column} = ?")
                params.append(value)
        if date_from:
            normalized_from, _ = self._date_boundary(date_from, is_end=False)
            where.append("a.created_at >= ?")
            params.append(normalized_from)
        if date_to:
            normalized_to, inclusive = self._date_boundary(date_to, is_end=True)
            where.append("a.created_at <= ?" if inclusive else "a.created_at < ?")
            params.append(normalized_to)
        return " AND ".join(where), params

    def _serialize_rows(
        self,
        rows: builtins.list[Any],
        target_context: dict[tuple[str, str], dict[str, Any]],
    ) -> builtins.list[dict[str, Any]]:
        items = []
        for row in rows:
            item = dict(row)
            item["before"] = json_value(item.pop("before_json"), None)
            item["after"] = json_value(item.pop("after_json"), None)
            item["target"] = self._target(
                item["entity_type"],
                item["entity_id"],
                target_context,
            )
            items.append(item)
        return items

    _target_context = staticmethod(_target_context)
    _target = staticmethod(_target)

    @staticmethod
    def _date_boundary(value: str, *, is_end: bool) -> tuple[str, bool]:
        clean_value = value.strip()
        if len(clean_value) == 10:
            try:
                parsed_date = date.fromisoformat(clean_value)
            except ValueError as exc:
                raise ValueError("审计日期必须是 YYYY-MM-DD 或 ISO 时间戳") from exc
            boundary_date = parsed_date + timedelta(days=1) if is_end else parsed_date
            boundary = datetime.combine(
                boundary_date,
                time.min,
                tzinfo=timezone.utc,
            )
            return boundary.isoformat(), False
        try:
            parsed_time = datetime.fromisoformat(clean_value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("审计日期必须是 YYYY-MM-DD 或 ISO 时间戳") from exc
        if parsed_time.tzinfo is not None:
            parsed_time = parsed_time.astimezone(timezone.utc)
        return parsed_time.isoformat(), True
