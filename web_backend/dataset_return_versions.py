from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from web_backend.common import insert_audit, json_text, new_id
from web_backend.database import Database
from web_backend.dataset_files import (
    DatasetRevisionConflict,
)
from web_backend.security import utc_now

logger = logging.getLogger(__name__)


class DatasetReturnVersionMixin:
    database: Database
    get: Callable[..., dict[str, Any] | None]
    _find_duplicate_return_import: Callable[..., dict[str, Any] | None]

    @staticmethod
    def _prepared_version(
        destination: Path,
        metadata: dict[str, str],
        inspection: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "id": new_id("dsv"),
            "file_path": str(destination),
            "original_name": metadata["original_name"],
            "content_type": metadata["content_type"],
            "size_bytes": destination.stat().st_size,
            "sha256": inspection["raw_sha256"],
            "row_count": inspection["row_count"],
            "column_count": inspection["column_count"],
            "schema_json": json_text(inspection["schema"]),
            "quality_json": json_text(inspection["quality"]),
            "change_note": metadata["change_note"],
        }

    @staticmethod
    def _insert_prepared_version(
        connection: Any,
        *,
        dataset_id: str,
        prepared: dict[str, Any],
        actor_id: str,
        now: str,
        expected_current_version: int | None,
    ) -> int:
        current = connection.execute(
            "SELECT current_version FROM datasets WHERE id = ?",
            (dataset_id,),
        ).fetchone()
        if current is None:
            raise ValueError("数据集不存在")
        if (
            expected_current_version is not None
            and int(current["current_version"]) != expected_current_version
        ):
            raise DatasetRevisionConflict("商品维度已被其他用户修改，请刷新后重试")
        version = int(current["current_version"]) + 1
        connection.execute(
            """
            INSERT INTO dataset_versions(
                id, dataset_id, version, file_path, original_name,
                content_type, size_bytes, sha256, row_count, column_count,
                schema_json, quality_json, change_note, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prepared["id"],
                dataset_id,
                version,
                prepared["file_path"],
                prepared["original_name"],
                prepared["content_type"],
                prepared["size_bytes"],
                prepared["sha256"],
                prepared["row_count"],
                prepared["column_count"],
                prepared["schema_json"],
                prepared["quality_json"],
                prepared["change_note"],
                actor_id,
                now,
            ),
        )
        connection.execute(
            """
            UPDATE datasets
            SET current_version = ?, updated_at = ?
            WHERE id = ?
            """,
            (version, now, dataset_id),
        )
        return version

    def _commit_return_import(
        self,
        *,
        dataset_id: str,
        dataset_name: str,
        source_key: str,
        prepared: dict[str, Any],
        import_record: dict[str, Any],
        actor_id: str,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            duplicate = self._find_duplicate_return_import(
                connection,
                raw_sha256=str(import_record["raw_sha256"]),
            )
            if duplicate is not None:
                return {
                    "dataset_id": str(duplicate["dataset_id"]),
                    "version_id": str(duplicate["version_id"]),
                    "duplicate": True,
                }
            connection.execute(
                """
                INSERT INTO datasets(
                    id, name, kind, description, source_key, usage_scope,
                    current_version, created_by, created_at, updated_at
                ) VALUES (?, ?, 'returns', '本次分析输入快照', ?, 'task_input', 0, ?, ?, ?)
                """,
                (dataset_id, dataset_name, source_key or None, actor_id, now, now),
            )
            version = self._insert_prepared_version(
                connection,
                dataset_id=dataset_id,
                prepared=prepared,
                actor_id=actor_id,
                now=now,
                expected_current_version=0,
            )
            insert_audit(
                connection,
                "dataset",
                dataset_id,
                "add_version",
                actor_id,
                after={
                    "version": version,
                    "version_id": prepared["id"],
                    "default_store": "",
                },
                created_at=now,
            )
            insert_audit(
                connection,
                "dataset",
                dataset_id,
                "create",
                actor_id,
                after={"name": dataset_name, "kind": "returns"},
                created_at=now,
            )
            connection.execute(
                """
                UPDATE datasets
                SET source_key = COALESCE(source_key, ?), updated_at = ?
                WHERE id = ?
                """,
                (source_key or None, now, dataset_id),
            )
            connection.execute(
                """
                INSERT INTO dataset_imports(
                    id, dataset_id, resulting_version_id, mode,
                    raw_file_path, original_name, content_type, size_bytes,
                    raw_sha256, row_count, column_count, schema_json,
                    quality_json, source_key, imported_row_count,
                    skipped_row_count, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    import_record["id"],
                    dataset_id,
                    prepared["id"],
                    "analyze_only",
                    import_record["raw_file_path"],
                    import_record["original_name"],
                    import_record["content_type"],
                    import_record["size_bytes"],
                    import_record["raw_sha256"],
                    import_record["row_count"],
                    import_record["column_count"],
                    import_record["schema_json"],
                    import_record["quality_json"],
                    source_key or None,
                    import_record["imported_row_count"],
                    import_record["skipped_row_count"],
                    actor_id,
                    now,
                ),
            )
            insert_audit(
                connection,
                "dataset",
                dataset_id,
                "import_returns",
                actor_id,
                after={
                    "import_id": import_record["id"],
                    "mode": "analyze_only",
                    "version_id": prepared["id"],
                    "raw_sha256": import_record["raw_sha256"],
                    "imported_row_count": import_record["imported_row_count"],
                    "skipped_row_count": import_record["skipped_row_count"],
                },
                created_at=now,
            )
            return {
                "dataset_id": dataset_id,
                "version_id": str(prepared["id"]),
                "duplicate": False,
            }

    @staticmethod
    def _cleanup_import_source(raw_destination: Path) -> None:
        raw_destination.unlink(missing_ok=True)
        try:
            raw_destination.parent.rmdir()
        except OSError as error:
            logger.warning("导入归档目录清理失败: error_type=%s", type(error).__name__)
