from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from web_backend.common import json_value, new_id
from web_backend.database import Database
from web_backend.datasets.return_import_preparation import (
    ReturnImportPreparationMixin,
    archive_return_source,
    validate_return_target,
)
from web_backend.security import utc_now
from web_backend.settings import Settings


class DatasetReturnImportMixin(ReturnImportPreparationMixin):
    database: Database
    settings: Settings
    get: Callable[..., dict[str, Any] | None]
    inspect_return_import: Callable[..., dict[str, Any]]
    _commit_appended_return_import: Callable[..., tuple[Any, ...]]
    _commit_return_import: Callable[..., dict[str, Any]]
    _cleanup_import_source: Callable[..., None]

    def _cleanup_staged_imports(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.database.transaction(immediate=True) as connection:
            rows = connection.execute(
                """
                SELECT id, temp_path FROM dataset_import_staging
                WHERE expires_at <= ? AND consumed_at IS NULL
                """,
                (now,),
            ).fetchall()
            connection.execute(
                """
                DELETE FROM dataset_import_staging
                WHERE expires_at <= ? AND consumed_at IS NULL
                """,
                (now,),
            )
        for row in rows:
            Path(str(row["temp_path"])).unlink(missing_ok=True)

    def import_staged_returns(
        self,
        *,
        inspection_id: str,
        actor_id: str,
        mode: str,
        dataset_id: str = "",
        name: str = "",
        change_note: str = "",
    ) -> dict[str, Any]:
        self._cleanup_staged_imports()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM dataset_import_staging WHERE id = ?",
                (inspection_id,),
            ).fetchone()
            if row is None:
                raise ValueError("文件检查记录已过期，请重新选择文件")
            if str(row["owner_id"]) != actor_id:
                raise ValueError("无权使用该文件检查记录")
            if row["consumed_at"]:
                raise ValueError("该文件已完成导入，不能重复提交")
            if not Path(str(row["temp_path"])).exists():
                raise ValueError("待导入文件已不存在，请重新选择文件")
            connection.execute(
                "UPDATE dataset_import_staging SET consumed_at = ? WHERE id = ?",
                (utc_now(), inspection_id),
            )
        path = Path(str(row["temp_path"]))
        try:
            result = self.import_returns(
                source_path=path,
                original_name=str(row["original_name"]),
                content_type=str(row["content_type"]),
                mode=mode,
                actor_id=actor_id,
                dataset_id=dataset_id,
                name=name,
                change_note=change_note,
                _inspection=json_value(row["inspection_json"], {}),
            )
        except Exception:
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    "UPDATE dataset_import_staging SET consumed_at = NULL WHERE id = ?",
                    (inspection_id,),
                )
            raise
        try:
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    "DELETE FROM dataset_import_staging WHERE id = ?",
                    (inspection_id,),
                )
        except Exception:
            pass
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return result

    def _return_import_target(
        self,
        *,
        mode: str,
        dataset_id: str,
        source_key: str,
    ) -> dict[str, Any] | None:
        if mode not in {"append", "replace"}:
            return None
        target = self.get(dataset_id)
        validate_return_target(target, source_key)
        return target

    @staticmethod
    def _validate_return_import_target(
        connection: Any,
        *,
        mode: str,
        dataset_id: str,
        source_key: str,
    ) -> None:
        if mode not in {"append", "replace"}:
            return
        target = connection.execute(
            """
            SELECT kind, usage_scope, source_key FROM datasets
            WHERE id = ? AND archived_at IS NULL
            """,
            (dataset_id,),
        ).fetchone()
        validate_return_target(dict(target) if target is not None else None, source_key)

    def import_returns(
        self,
        *,
        source_path: Path,
        original_name: str,
        content_type: str,
        mode: str,
        actor_id: str,
        dataset_id: str = "",
        name: str = "",
        change_note: str = "",
        _inspection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if mode not in {"analyze_only", "create", "append", "replace"}:
            raise ValueError("未知的用户反馈数据导入方式")
        inspection = _inspection or self.inspect_return_import(
            source_path,
            original_name,
        )
        duplicate_result = self._duplicate_return_import(
            mode=mode,
            dataset_id=dataset_id,
            inspection=inspection,
        )
        if duplicate_result is not None:
            return duplicate_result
        target = self._return_import_target(
            mode=mode,
            dataset_id=dataset_id,
            source_key=str(inspection["source_key"]),
        )

        import_id = new_id("dataset_import")
        raw_destination = (
            self.settings.data_dir
            / "imports"
            / import_id
            / f"source{source_path.suffix.lower()}"
        )
        imported_row_count = int(inspection["row_count"])
        skipped_row_count = 0
        generated_note = change_note.strip()
        effective_dataset_id = dataset_id
        try:
            import_record = archive_return_source(
                source_path,
                raw_destination,
                inspection,
                {
                    "id": import_id,
                    "original_name": original_name,
                    "content_type": content_type,
                    "imported_row_count": imported_row_count,
                    "skipped_row_count": skipped_row_count,
                },
            )
            if mode != "append":
                (
                    effective_dataset_id,
                    dataset_name,
                    dataset_description,
                    usage_scope,
                    prepared,
                ) = self._prepare_non_appended_return_import(
                    mode,
                    target,
                    source_path,
                    inspection,
                    {
                        "dataset_id": dataset_id,
                        "name": name,
                        "original_name": original_name,
                        "content_type": content_type,
                        "generated_note": generated_note,
                    },
                )
            else:
                assert target is not None
                (
                    prepared,
                    imported_row_count,
                    skipped_row_count,
                    outcome,
                ) = self._commit_appended_return_import(
                    dataset_id=effective_dataset_id,
                    target=target,
                    source_path=source_path,
                    original_name=original_name,
                    change_note=generated_note,
                    source_key=str(inspection["source_key"]),
                    import_record=import_record,
                    actor_id=actor_id,
                )
            if mode != "append":
                outcome = self._commit_return_import(
                    mode=mode,
                    dataset_id=effective_dataset_id,
                    dataset_name=dataset_name,
                    dataset_description=dataset_description,
                    usage_scope=usage_scope,
                    source_key=str(inspection["source_key"]),
                    prepared=prepared,
                    import_record=import_record,
                    actor_id=actor_id,
                    expected_current_version=(
                        0 if mode in {"create", "analyze_only"} else None
                    ),
                )
        except Exception:
            self._cleanup_import_source(raw_destination)
            raise

        if outcome["duplicate"]:
            self._cleanup_import_source(raw_destination)
            imported_row_count = 0
            skipped_row_count = int(inspection["row_count"])
        return self._return_import_result(
            outcome,
            target,
            inspection,
            mode,
            {
                "imported_row_count": imported_row_count,
                "skipped_row_count": skipped_row_count,
            },
        )
