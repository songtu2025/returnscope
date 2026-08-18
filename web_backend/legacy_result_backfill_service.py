from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from web_backend.agent_runner import AgentRunner, IncompleteResultCheckpoint
from web_backend.common import json_text, json_value, new_id
from web_backend.database import Database
from web_backend.security import utc_now

SYSTEM_ACTOR_ID = "system-legacy-result-backfill"
PREVIEW_VERSION = "legacy-classification-result-backfill-v1"


class LegacyResultBackfillConflict(ValueError):
    pass


class LegacyResultBackfillService:
    def __init__(self, database: Database, runner: AgentRunner) -> None:
        self.database = database
        self.runner = runner

    def preview(self) -> dict[str, Any]:
        buckets: dict[str, list[dict[str, Any]]] = {
            "ready": [],
            "unavailable": [],
            "incomplete": [],
            "already_published": [],
        }
        for row in self._rows():
            item = self._base_item(row)
            if row["result_version_id"] or row["result_publish_status"] == "published":
                buckets["already_published"].append(item)
                continue
            try:
                inspected = self.runner.inspect_completed_result(
                    str(row["task_id"]),
                    str(row["segment_id"]),
                )
                item.update(inspected)
                category = "ready"
            except IncompleteResultCheckpoint as exc:
                item["reason"] = str(exc)
                category = "incomplete"
            except Exception as exc:
                item["reason"] = str(exc)[:500]
                category = "unavailable"
            buckets[category].append(item)

        for items in buckets.values():
            items.sort(key=lambda value: (value["task_id"], value["segment_id"]))
        hash_input = {
            "version": PREVIEW_VERSION,
            "items": [
                {
                    "category": category,
                    **item["_fingerprint"],
                }
                for category, items in buckets.items()
                for item in items
            ],
        }
        preview_hash = hashlib.sha256(
            json_text(hash_input).encode("utf-8")
        ).hexdigest()
        output = {
            "mode": "preview",
            "preview_hash": preview_hash,
            "counts": {name: len(items) for name, items in buckets.items()},
        }
        output.update(
            {
                name: [self._public_item(item) for item in items]
                for name, items in buckets.items()
            }
        )
        return output

    def apply(self, preview_hash: str) -> dict[str, Any]:
        clean_hash = preview_hash.strip()
        if not clean_hash:
            raise LegacyResultBackfillConflict("必须提供预览返回的 preview_hash")
        preview = self.preview()
        if preview["preview_hash"] != clean_hash:
            replay = self._applied_segments(clean_hash)
            if replay:
                return self._replay_result(clean_hash, replay)
            raise LegacyResultBackfillConflict(
                "回填候选或检查点已经变化，请重新预览后再执行"
            )

        success: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        skipped = [
            {**item, "reason": "分类结果已发布"}
            for item in preview["already_published"]
        ]
        skipped.extend(preview["unavailable"])
        skipped.extend(preview["incomplete"])
        for item in preview["ready"]:
            task_id = str(item["task_id"])
            segment_id = str(item["segment_id"])
            try:
                prepared = self._mark_publishing(task_id, segment_id, clean_hash)
                if not prepared:
                    skipped.append({**item, "reason": "片段状态已变化"})
                    continue
                version = self.runner.retry_result_publish(task_id, segment_id)
                success.append(
                    {
                        **item,
                        "result_version_id": version["version_id"],
                        "version": version["version"],
                        "quality_status": version["quality_status"],
                    }
                )
            except Exception as exc:
                failed.append({**item, "reason": str(exc)[:500]})
        return {
            "mode": "apply",
            "preview_hash": clean_hash,
            "counts": {
                "success": len(success),
                "failed": len(failed),
                "skipped": len(skipped),
            },
            "success": success,
            "failed": failed,
            "skipped": skipped,
        }

    def _rows(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT s.id AS segment_id, s.task_id, s.segment_key,
                       s.agent_key, s.status, s.result_version_id,
                       s.result_publish_status, s.result_json_path,
                       s.classification_keys_json, s.scope_json,
                       s.logic_version, s.taxonomy_version,
                       s.model_policy_version, s.claims_version,
                       s.result_version, t.store,
                       t.listing AS task_listing, t.snapshot_json,
                       t.dataset_version_id, t.product_version_id,
                       returns.sha256 AS dataset_sha256,
                       products.sha256 AS product_sha256
                FROM task_segments s
                JOIN tasks t ON t.id = s.task_id
                JOIN dataset_versions returns ON returns.id = t.dataset_version_id
                JOIN dataset_versions products ON products.id = t.product_version_id
                WHERE s.status IN ('completed', 'completed_with_errors')
                  AND (
                      s.result_version_id IS NOT NULL
                      OR s.result_publish_status = 'published'
                      OR (
                          s.result_version_id IS NULL
                          AND LOWER(COALESCE(s.result_publish_status, ''))
                              IN ('', 'legacy')
                      )
                  )
                ORDER BY s.task_id, s.id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _base_item(row: dict[str, Any]) -> dict[str, Any]:
        scope = json_value(row.get("scope_json"), {})
        snapshot = json_value(row.get("snapshot_json"), {})
        normalized_scope = json.dumps(
            scope,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        normalized_snapshot = json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        snapshot_scope = snapshot.get("scope", {}) if isinstance(snapshot, dict) else {}
        snapshot_scope_mode = (
            snapshot_scope.get("mode") if isinstance(snapshot_scope, dict) else None
        )
        try:
            raw_keys = json_value(row["classification_keys_json"], [])
            classification_keys = (
                sorted({str(value) for value in raw_keys})
                if isinstance(raw_keys, list)
                else []
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            classification_keys = []
        checkpoint_path = Path(str(row.get("result_json_path") or ""))
        checkpoint_hash = (
            hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
            if checkpoint_path.is_file()
            else None
        )
        fingerprint = {
            "segment_id": str(row["segment_id"]),
            "task_id": str(row["task_id"]),
            "status": str(row["status"]),
            "result_version_id": row["result_version_id"],
            "result_publish_status": row["result_publish_status"],
            "dataset_version_id": str(row["dataset_version_id"]),
            "product_version_id": str(row["product_version_id"]),
            "dataset_sha256": str(row["dataset_sha256"]),
            "product_sha256": str(row["product_sha256"]),
            "task_store": row["store"],
            "task_listing": row["task_listing"],
            "snapshot_scope_mode": snapshot_scope_mode,
            "snapshot_sha256": hashlib.sha256(
                normalized_snapshot.encode("utf-8")
            ).hexdigest(),
            "segment_scope_json": normalized_scope,
            "agent_key": str(row["agent_key"]),
            "logic_version": row["logic_version"],
            "taxonomy_version": str(row["taxonomy_version"]),
            "model_policy_version": row["model_policy_version"],
            "claims_version": row["claims_version"],
            "result_version": int(row["result_version"] or 0),
            "classification_keys": classification_keys,
            "checkpoint_path": str(row.get("result_json_path") or ""),
            "checkpoint_sha256": checkpoint_hash,
        }
        return {
            "segment_id": str(row["segment_id"]),
            "task_id": str(row["task_id"]),
            "segment_key": str(row["segment_key"]),
            "listing": scope.get("listing") or row["task_listing"],
            "agent_key": str(row["agent_key"]),
            "status": str(row["status"]),
            "result_publish_status": row["result_publish_status"],
            "result_version_id": row["result_version_id"],
            "classification_key_count": len(classification_keys),
            "_fingerprint": fingerprint,
        }

    @staticmethod
    def _public_item(item: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in item.items()
            if key not in {"_fingerprint", "checkpoint_path"}
        }

    def _mark_publishing(
        self,
        task_id: str,
        segment_id: str,
        preview_hash: str,
    ) -> bool:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            segment = connection.execute(
                """
                SELECT status, result_version_id, result_publish_status
                FROM task_segments WHERE id = ? AND task_id = ?
                """,
                (segment_id, task_id),
            ).fetchone()
            if (
                segment is None
                or segment["status"] not in {"completed", "completed_with_errors"}
                or segment["result_version_id"] is not None
                or str(segment["result_publish_status"] or "").lower()
                not in {"", "legacy"}
            ):
                return False
            connection.execute(
                """
                INSERT OR IGNORE INTO users(
                    id, email, display_name, password_hash, active, created_at
                ) VALUES (?, 'system-legacy-result-backfill@local',
                          '系统迁移', 'no-interactive-login', 0, ?)
                """,
                (SYSTEM_ACTOR_ID, now),
            )
            updated = connection.execute(
                """
                UPDATE task_segments
                SET result_publish_status = 'publishing',
                    result_publish_error = NULL, revision = revision + 1,
                    heartbeat_at = ?
                WHERE id = ? AND task_id = ?
                  AND status IN ('completed', 'completed_with_errors')
                  AND result_version_id IS NULL
                  AND LOWER(COALESCE(result_publish_status, '')) IN ('', 'legacy')
                """,
                (now, segment_id, task_id),
            )
            if updated.rowcount != 1:
                return False
            event_data = {
                "segment_id": segment_id,
                "preview_hash": preview_hash,
                "actor": SYSTEM_ACTOR_ID,
            }
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'legacy_result_backfill_started', '生成结果',
                          '正在回填历史 Listing 分类结果', ?, ?, ?)
                """,
                (
                    task_id,
                    SYSTEM_ACTOR_ID,
                    json_text(event_data),
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO audit_logs(
                    id, entity_type, entity_id, action, before_json,
                    after_json, actor_id, created_at
                ) VALUES (?, 'task_segment', ?, 'legacy_result_backfill_prepare',
                          ?, ?, ?, ?)
                """,
                (
                    new_id("audit"),
                    segment_id,
                    json_text(
                        {
                            "result_publish_status": segment[
                                "result_publish_status"
                            ]
                        }
                    ),
                    json_text(
                        {
                            "result_publish_status": "publishing",
                            **event_data,
                        }
                    ),
                    SYSTEM_ACTOR_ID,
                    now,
                ),
            )
        return True

    def _applied_segments(self, preview_hash: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT a.entity_id AS segment_id, s.task_id,
                       s.result_version_id, s.result_publish_status
                FROM audit_logs a
                LEFT JOIN task_segments s ON s.id = a.entity_id
                WHERE a.action = 'legacy_result_backfill_prepare'
                  AND json_extract(a.after_json, '$.preview_hash') = ?
                ORDER BY a.entity_id
                """,
                (preview_hash,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _replay_result(
        preview_hash: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        skipped = [
            {
                **row,
                "reason": "该 preview_hash 已执行，不重复创建结果版本",
            }
            for row in rows
        ]
        return {
            "mode": "apply",
            "preview_hash": preview_hash,
            "counts": {"success": 0, "failed": 0, "skipped": len(skipped)},
            "success": [],
            "failed": [],
            "skipped": skipped,
        }
