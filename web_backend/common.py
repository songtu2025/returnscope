from __future__ import annotations

import json
import secrets
from typing import Any

from web_backend.database import Database
from web_backend.security import utc_now


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_value(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    return json.loads(value)


def add_audit(
    database: Database,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_id: str,
    before: Any = None,
    after: Any = None,
) -> None:
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO audit_logs(
                id, entity_type, entity_id, action, before_json,
                after_json, actor_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("audit"),
                entity_type,
                entity_id,
                action,
                json_text(before) if before is not None else None,
                json_text(after) if after is not None else None,
                actor_id,
                utc_now(),
            ),
        )


def list_audit(
    database: Database,
    entity_type: str,
    entity_id: str,
) -> list[dict[str, Any]]:
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT a.*, u.display_name AS actor_name
            FROM audit_logs a
            JOIN users u ON u.id = a.actor_id
            WHERE a.entity_type = ? AND a.entity_id = ?
            ORDER BY a.created_at DESC
            """,
            (entity_type, entity_id),
        ).fetchall()
    output = []
    for row in rows:
        item = dict(row)
        item["before"] = json_value(item.pop("before_json"))
        item["after"] = json_value(item.pop("after_json"))
        output.append(item)
    return output
