from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from web_backend.common import new_id
from web_backend.database import Database
from web_backend.security import utc_now


@dataclass(frozen=True, kw_only=True)
class _ValidationTarget:
    kind: str
    target_id: str
    connection_id: str
    config_version_id: str


class _ValidationRunRecords:
    """读取、创建、领取和恢复验证记录，保证事件与状态同步写入。"""

    database: Database

    def get_validation_run(self, run_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT r.*, u.display_name AS creator_name
                FROM api_validation_runs r
                JOIN users u ON u.id = r.created_by
                WHERE r.id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["items"] = json.loads(item.pop("items_json"))
        return item

    def latest_active_validation_run(
        self,
        connection_id: str,
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id FROM api_validation_runs
                WHERE connection_id = ? AND status IN ('queued', 'running')
                ORDER BY created_at DESC LIMIT 1
                """,
                (connection_id,),
            ).fetchone()
        return self.get_validation_run(str(row["id"])) if row else None

    def validation_events(
        self,
        run_id: str,
        after_id: int = 0,
    ) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM api_validation_events
                WHERE run_id = ? AND id > ?
                ORDER BY id ASC
                """,
                (run_id, after_id),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["data"] = json.loads(item.pop("data_json") or "{}")
            output.append(item)
        return output

    def recover_validation_runs(self) -> None:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            rows = connection.execute(
                """
                SELECT id FROM api_validation_runs
                WHERE status IN ('queued', 'running')
                """
            ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    UPDATE api_validation_runs
                    SET status = 'failed', stage = 'interrupted',
                        error_category = 'interrupted',
                        error_message = '服务重启，验证已中断',
                        suggestion = '请重新发起验证', completed_at = ?
                    WHERE id = ?
                    """,
                    (now, row["id"]),
                )
                connection.execute(
                    """
                    INSERT INTO api_validation_events(
                        run_id, event_type, stage, message, data_json,
                        created_at
                    ) VALUES (?, 'failed', 'interrupted',
                              '服务重启，验证已中断', '{}', ?)
                    """,
                    (row["id"], now),
                )

    def _create_validation_run(
        self,
        target: _ValidationTarget,
        actor_id: str,
        config: dict[str, Any],
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        kind = target.kind
        target_id = target.target_id
        connection_id = target.connection_id
        config_version_id = target.config_version_id
        now = utc_now()
        run_id = new_id("validation")
        with self.database.transaction(immediate=True) as connection:
            active = connection.execute(
                """
                SELECT id FROM api_validation_runs
                WHERE kind = ? AND target_id = ?
                  AND status IN ('queued', 'running')
                ORDER BY created_at DESC LIMIT 1
                """,
                (kind, target_id),
            ).fetchone()
            if active:
                run_id = str(active["id"])
            else:
                connection.execute(
                    """
                    INSERT INTO api_validation_runs(
                        id, kind, target_id, connection_id,
                        config_version_id, status, stage, endpoint,
                        timeout_seconds, items_json, total_count,
                        created_by, created_at
                    ) VALUES (?, ?, ?, ?, ?, 'queued', 'queued', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        kind,
                        target_id,
                        connection_id,
                        config_version_id,
                        f"{str(config['base_url']).rstrip('/')}/responses",
                        int(config["timeout_seconds"]),
                        json.dumps(items, ensure_ascii=False),
                        len(items),
                        actor_id,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO api_validation_events(
                        run_id, event_type, stage, message, data_json,
                        created_at
                    ) VALUES (?, 'queued', 'queued', '验证已进入队列', ?, ?)
                    """,
                    (
                        run_id,
                        json.dumps(
                            {"kind": kind, "total_count": len(items)},
                            ensure_ascii=False,
                        ),
                        now,
                    ),
                )
        return self.get_validation_run(run_id) or {}

    def _start_validation_run(self, run_id: str) -> bool:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            updated = connection.execute(
                """
                UPDATE api_validation_runs
                SET status = 'running', stage = 'preparing', started_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, run_id),
            )
            if updated.rowcount != 1:
                return False
            connection.execute(
                """
                INSERT INTO api_validation_events(
                    run_id, event_type, stage, message, data_json,
                    created_at
                ) VALUES (?, 'started', 'preparing',
                          '开始执行真实模型验证', '{}', ?)
                """,
                (run_id, now),
            )
        return True
