from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from web_backend.common import json_value, new_id
from web_backend.database import Database
from web_backend.dataset_return_versions import DatasetVersionWrite
from web_backend.datasets.return_import_preparation import (
    ReturnImportPreparationMixin,
    archive_return_source,
)
from web_backend.security import utc_now
from web_backend.settings import Settings

logger = logging.getLogger(__name__)


class DatasetReturnImportMixin(ReturnImportPreparationMixin):
    database: Database
    settings: Settings
    get: Callable[..., dict[str, Any] | None]
    inspect_return_import: Callable[..., dict[str, Any]]
    _commit_return_import: Callable[..., dict[str, Any]]
    _prepare_dataset_file: Callable[..., dict[str, Any]]
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
        except Exception as error:
            logger.warning("导入检查记录清理失败: error_type=%s", type(error).__name__)
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            logger.warning("导入临时文件清理失败: error_type=%s", type(error).__name__)
        return result

    def import_returns(
        self,
        *,
        source_path: Path,
        original_name: str,
        content_type: str,
        mode: str,
        actor_id: str,
        name: str = "",
        change_note: str = "",
        _inspection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if mode != "analyze_only":
            raise ValueError("仅支持分析本批数据，长期数据源导入已下线")
        inspection = _inspection or self.inspect_return_import(
            source_path,
            original_name,
        )
        if inspection["quality"]["missing_store_rows"]:
            raise ValueError("文件中存在缺少店铺/站点的记录，请补齐后重新导入")
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
        effective_dataset_id = new_id("ds")
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
            prepared = self._prepare_dataset_file(
                source_path,
                "returns",
                inspection,
                {
                    "original_name": original_name,
                    "content_type": content_type,
                    "change_note": generated_note or "导入本次分析数据",
                },
            )
            outcome = self._commit_return_import(
                write=DatasetVersionWrite(
                    dataset_id=effective_dataset_id,
                    prepared=prepared,
                    actor_id=actor_id,
                    expected_current_version=0,
                ),
                dataset_name=name.strip() or str(inspection["suggested_name"]),
                source_key=str(inspection["source_key"]),
                import_record=import_record,
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
            inspection,
            {
                "imported_row_count": imported_row_count,
                "skipped_row_count": skipped_row_count,
            },
        )
