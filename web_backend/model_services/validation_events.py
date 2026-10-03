from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from web_backend.common import add_audit
from web_backend.database import Database
from web_backend.security import utc_now


@dataclass(frozen=True, kw_only=True)
class _ValidationItemEvent:
    event_type: str
    message: str
    data: dict[str, Any] | None = None


class _ValidationRunEvents:
    """保存单模型进度、失败跳过、验证结束及配置审计事件。"""

    database: Database

    def _update_validation_item(
        self,
        run_id: str,
        index: int,
        changes: dict[str, Any],
        event: _ValidationItemEvent,
    ) -> None:
        event_type = event.event_type
        message = event.message
        data = event.data
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT items_json FROM api_validation_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                return
            items = json.loads(row["items_json"])
            items[index].update(changes)
            completed_count = sum(
                item["status"] in {"passed", "failed"} for item in items
            )
            connection.execute(
                """
                UPDATE api_validation_runs
                SET items_json = ?, stage = ?, completed_count = ?
                WHERE id = ?
                """,
                (
                    json.dumps(items, ensure_ascii=False),
                    str(items[index]["stage"]),
                    completed_count,
                    run_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO api_validation_events(
                    run_id, event_type, stage, message, model_key,
                    data_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    event_type,
                    str(items[index]["stage"]),
                    message,
                    str(items[index]["model_key"]),
                    json.dumps(data or {}, ensure_ascii=False),
                    now,
                ),
            )

    def _skip_validation_items(self, run_id: str, start_index: int) -> None:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT items_json FROM api_validation_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                return
            items = json.loads(row["items_json"])
            for item in items[start_index:]:
                item.update(
                    {
                        "status": "skipped",
                        "stage": "skipped",
                        "message": "前序模型验证失败，已停止后续验证",
                    }
                )
                connection.execute(
                    """
                    INSERT INTO api_validation_events(
                        run_id, event_type, stage, message, model_key,
                        data_json, created_at
                    ) VALUES (?, 'model_skipped', 'skipped', ?, ?, '{}', ?)
                    """,
                    (
                        run_id,
                        item["message"],
                        item["model_key"],
                        now,
                    ),
                )
            connection.execute(
                "UPDATE api_validation_runs SET items_json = ? WHERE id = ?",
                (json.dumps(items, ensure_ascii=False), run_id),
            )

    def _finish_validation_run(
        self,
        run: dict[str, Any],
        status: str,
        error_category: str | None,
        message: str,
        suggestion: str | None,
    ) -> None:
        now = utc_now()
        stage = "passed" if status == "passed" else "failed"
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE api_validation_runs
                SET status = ?, stage = ?, error_category = ?,
                    error_message = ?, suggestion = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    stage,
                    error_category,
                    None if status == "passed" else message,
                    suggestion,
                    now,
                    run["id"],
                ),
            )
            connection.execute(
                """
                INSERT INTO api_validation_events(
                    run_id, event_type, stage, message, data_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run["id"],
                    "completed" if status == "passed" else "failed",
                    stage,
                    message,
                    json.dumps(
                        {
                            "error_category": error_category,
                            "suggestion": suggestion,
                        },
                        ensure_ascii=False,
                    ),
                    now,
                ),
            )

    def _set_config_validation(
        self,
        version_id: str,
        status: str,
        message: str,
        actor_id: str,
    ) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE api_config_versions
                SET validation_status = ?, validation_message = ?,
                    validated_at = ?
                WHERE id = ?
                """,
                (status, message, now, version_id),
            )
        add_audit(
            self.database,
            "api_config_version",
            version_id,
            "validate",
            actor_id,
            after={"status": status, "message": message},
        )
