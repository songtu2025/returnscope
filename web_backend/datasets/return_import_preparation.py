import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from web_backend.common import json_text


def archive_return_source(
    source_path: Path,
    raw_destination: Path,
    inspection: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    raw_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, raw_destination)
    return {
        "id": metadata["id"],
        "raw_file_path": str(raw_destination),
        "original_name": metadata["original_name"],
        "content_type": metadata["content_type"],
        "size_bytes": raw_destination.stat().st_size,
        "raw_sha256": inspection["raw_sha256"],
        "row_count": inspection["row_count"],
        "column_count": inspection["column_count"],
        "schema_json": json_text(inspection["schema"]),
        "quality_json": json_text(inspection["quality"]),
        "imported_row_count": metadata["imported_row_count"],
        "skipped_row_count": metadata["skipped_row_count"],
    }


class ReturnImportPreparationMixin:
    get: Callable[..., dict[str, Any] | None]

    def _return_import_result(
        self,
        outcome: dict[str, Any],
        inspection: dict[str, Any],
        summary: dict[str, int],
    ) -> dict[str, Any]:
        result_dataset_id = str(outcome["dataset_id"])
        refreshed = self.get(result_dataset_id) or {}
        return {
            "dataset": refreshed,
            "version_id": str(outcome["version_id"]),
            "duplicate": bool(outcome["duplicate"]),
            "mode": "analyze_only",
            "inspection": inspection,
            "summary": summary,
        }

    @staticmethod
    def _find_duplicate_return_import(
        connection: Any,
        *,
        raw_sha256: str,
    ) -> dict[str, Any] | None:
        params = (raw_sha256,)
        duplicate = connection.execute(
            """
            SELECT i.id AS import_id, i.dataset_id,
                   i.resulting_version_id AS version_id,
                   i.mode, i.created_at,
                   d.name AS dataset_name, d.usage_scope
            FROM dataset_imports i
            JOIN datasets d ON d.id = i.dataset_id
            WHERE i.raw_sha256 = ? AND d.archived_at IS NULL
              AND d.kind = 'returns' AND d.usage_scope = 'task_input'
            ORDER BY i.created_at DESC, i.id DESC
            LIMIT 1
            """,
            params,
        ).fetchone()
        if duplicate is None:
            duplicate = connection.execute(
                """
                SELECT NULL AS import_id, v.dataset_id,
                       v.id AS version_id, 'legacy' AS mode,
                       v.created_at, d.name AS dataset_name,
                       d.usage_scope
                FROM dataset_versions v
                JOIN datasets d ON d.id = v.dataset_id
                WHERE v.sha256 = ? AND d.archived_at IS NULL
                  AND d.kind = 'returns' AND d.usage_scope = 'task_input'
                ORDER BY v.created_at DESC, v.id DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
        return dict(duplicate) if duplicate is not None else None
