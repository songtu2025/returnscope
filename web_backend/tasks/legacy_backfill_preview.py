from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from web_backend.agent_runner import AgentRunner, IncompleteResultCheckpoint
from web_backend.common import json_value


def _normalized_backfill_scope(
    scope: Any,
    snapshot: Any,
) -> tuple[str, str, Any]:
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
    return normalized_scope, normalized_snapshot, snapshot_scope_mode


def _backfill_fingerprint(
    row: dict[str, Any],
    classification_keys: list[str],
    checkpoint_hash: str | None,
    scope_state: tuple[str, str, Any],
) -> dict[str, Any]:
    normalized_scope, normalized_snapshot, snapshot_scope_mode = scope_state
    return {
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


class LegacyBackfillPreviewMixin:
    """整理历史结果的预览分类及保持原口径的指纹。"""

    runner: AgentRunner

    @staticmethod
    def _base_item(row: dict[str, Any]) -> dict[str, Any]:
        scope = json_value(row.get("scope_json"), {})
        snapshot = json_value(row.get("snapshot_json"), {})
        scope_state = _normalized_backfill_scope(scope, snapshot)
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
        fingerprint = _backfill_fingerprint(
            row,
            classification_keys,
            checkpoint_hash,
            scope_state,
        )
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

    def _inspect_backfill_item(
        self,
        row: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        item = self._base_item(row)
        if row["result_version_id"] or row["result_publish_status"] == "published":
            return "already_published", item
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
        return category, item
