from __future__ import annotations

from typing import Any


def _target_context(
    connection: Any,
    audit_rows: list[Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    ids_by_type: dict[str, set[str]] = {}
    for row in audit_rows:
        ids_by_type.setdefault(str(row["entity_type"]), set()).add(
            str(row["entity_id"])
        )

    context: dict[tuple[str, str], dict[str, Any]] = {}

    def load(entity_type: str, query: str) -> None:
        entity_ids = sorted(ids_by_type.get(entity_type, set()))
        if not entity_ids:
            return
        placeholders = ",".join("?" for _ in entity_ids)
        rows = connection.execute(
            query.format(placeholders=placeholders),
            tuple(entity_ids),
        ).fetchall()
        for row in rows:
            item = dict(row)
            context[(entity_type, str(item["id"]))] = item

    load("task", "SELECT id FROM tasks WHERE id IN ({placeholders})")
    load(
        "task_segment",
        """
        SELECT segment.id, segment.task_id
        FROM task_segments segment
        JOIN tasks task ON task.id = segment.task_id
        WHERE segment.id IN ({placeholders})
        """,
    )
    load(
        "classification_result_version",
        """
        SELECT id FROM classification_result_versions
        WHERE id IN ({placeholders})
        """,
    )
    load(
        "classification_result",
        """
        SELECT id, result_version_id
        FROM (
            SELECT result.id, version.id AS result_version_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY result.id
                       ORDER BY version.version_no DESC,
                                version.published_at DESC,
                                version.id ASC
                   ) AS position
            FROM classification_results result
            JOIN classification_result_versions version
              ON version.result_id = result.id
             AND version.publish_status = 'published'
            WHERE result.id IN ({placeholders})
        ) latest
        WHERE position = 1
        """,
    )
    load(
        "review",
        """
        SELECT id, workflow_status FROM review_records
        WHERE id IN ({placeholders})
        """,
    )
    load(
        "review_batch",
        "SELECT id FROM review_batches WHERE id IN ({placeholders})",
    )
    load(
        "dataset",
        "SELECT id, kind FROM datasets WHERE id IN ({placeholders})",
    )
    load(
        "api_connection",
        "SELECT id FROM api_connections WHERE id IN ({placeholders})",
    )
    load(
        "api_config_version",
        """
        SELECT id, connection_id FROM api_config_versions
        WHERE id IN ({placeholders})
        """,
    )
    load(
        "api_model",
        """
        SELECT id, connection_id FROM api_models
        WHERE id IN ({placeholders})
        """,
    )
    load("user", "SELECT id FROM users WHERE id IN ({placeholders})")
    load(
        "analysis_dashboard",
        """
        SELECT id, current_version_id FROM analysis_dashboards
        WHERE id IN ({placeholders})
        """,
    )
    return context


def _target(
    entity_type: str,
    entity_id: str,
    context: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    source = context.get((entity_type, entity_id))
    if source is None:
        return None
    target = _analysis_target(entity_type, entity_id, source)
    if target is not None:
        return target
    return _configuration_target(entity_type, entity_id, source)


def _analysis_target(
    entity_type: str,
    entity_id: str,
    source: dict[str, Any],
) -> dict[str, Any] | None:
    for resolver in (_task_target, _result_target, _review_target):
        target = resolver(entity_type, entity_id, source)
        if target is not None:
            return target
    if entity_type == "dataset" and source["kind"] == "products":
        return {
            "route": "data",
            "dataset_id": entity_id,
            "view": source["kind"],
        }
    if entity_type == "analysis_dashboard":
        target = {
            "route": "analysis-dashboards",
            "dashboard_id": entity_id,
        }
        if source["current_version_id"]:
            target["version_id"] = source["current_version_id"]
        return target
    return None


def _task_target(
    entity_type: str, entity_id: str, source: dict[str, Any]
) -> dict[str, Any] | None:
    if entity_type == "task":
        return {"route": "tasks", "task_id": entity_id}
    if entity_type == "task_segment":
        return {
            "route": "tasks",
            "task_id": source["task_id"],
            "segment_id": entity_id,
        }
    return None


def _result_target(
    entity_type: str, entity_id: str, source: dict[str, Any]
) -> dict[str, Any] | None:
    if entity_type == "classification_result_version":
        return {
            "route": "classification-results",
            "result_version_id": entity_id,
        }
    if entity_type == "classification_result":
        return {
            "route": "classification-results",
            "result_version_id": source["result_version_id"],
        }
    return None


def _review_target(
    entity_type: str, entity_id: str, source: dict[str, Any]
) -> dict[str, Any] | None:
    if entity_type == "review":
        return {
            "route": "review",
            "review_id": entity_id,
            "workflow_status": source["workflow_status"],
        }
    if entity_type == "review_batch":
        return {"route": "review-center", "batch_id": entity_id}
    return None


def _configuration_target(
    entity_type: str,
    entity_id: str,
    source: dict[str, Any],
) -> dict[str, Any] | None:
    if entity_type == "api_connection":
        return {
            "route": "api",
            "tab": "api",
            "connection_id": entity_id,
        }
    if entity_type == "api_config_version":
        return {
            "route": "api",
            "tab": "api",
            "connection_id": source["connection_id"],
            "config_version_id": entity_id,
        }
    if entity_type == "api_model":
        return {
            "route": "api",
            "tab": "models",
            "connection_id": source["connection_id"],
            "model_id": entity_id,
        }
    if entity_type == "user":
        return {
            "route": "team",
            "tab": "users",
            "user_id": entity_id,
        }
    return None
