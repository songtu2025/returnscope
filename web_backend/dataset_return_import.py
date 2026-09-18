from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from web_backend.common import json_text, json_value, new_id
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.settings import Settings


class DatasetReturnImportMixin:
    database: Database
    settings: Settings
    get: Callable[..., dict[str, Any] | None]
    inspect_return_import: Callable[..., dict[str, Any]]
    _prepare_return_version: Callable[..., dict[str, Any]]
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

    def _duplicate_return_import(
        self,
        *,
        mode: str,
        dataset_id: str,
        inspection: dict[str, Any],
    ) -> dict[str, Any] | None:
        duplicate = inspection.get("duplicate")
        duplicate_in_target = duplicate and (
            mode == "analyze_only"
            or (mode == "create" and duplicate.get("usage_scope") == "managed")
            or str(duplicate["dataset_id"]) == dataset_id
        )
        if not duplicate_in_target:
            return None
        existing = self.get(str(duplicate["dataset_id"]))
        if existing is None:
            return None
        return {
            "dataset": existing,
            "version_id": str(duplicate["version_id"]),
            "duplicate": True,
            "mode": mode,
            "inspection": inspection,
            "summary": {
                "imported_row_count": 0,
                "skipped_row_count": int(inspection["row_count"]),
            },
        }

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
        if target is None or target["kind"] != "returns":
            raise ValueError("请选择有效的用户反馈数据源")
        if target.get("usage_scope") != "managed":
            raise ValueError("一次性任务数据不能作为长期数据源更新")
        target_source_key = str(target.get("source_key") or "")
        if target_source_key and source_key and target_source_key != source_key:
            raise ValueError("上传文件与所选数据源的店铺/站点不一致")
        return target

    @staticmethod
    def _find_duplicate_return_import(
        connection: Any,
        *,
        raw_sha256: str,
        mode: str,
        dataset_id: str,
    ) -> dict[str, Any] | None:
        params = (raw_sha256, mode, mode, mode, dataset_id)
        duplicate = connection.execute(
            """
            SELECT i.id AS import_id, i.dataset_id,
                   i.resulting_version_id AS version_id,
                   i.mode, i.created_at,
                   d.name AS dataset_name, d.usage_scope
            FROM dataset_imports i
            JOIN datasets d ON d.id = i.dataset_id
            WHERE i.raw_sha256 = ? AND d.archived_at IS NULL
              AND (
                  ? = 'analyze_only'
                  OR (? = 'create' AND d.usage_scope = 'managed')
                  OR (? IN ('append', 'replace') AND i.dataset_id = ?)
              )
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
                  AND (
                      ? = 'analyze_only'
                      OR (? = 'create' AND d.usage_scope = 'managed')
                      OR (? IN ('append', 'replace') AND v.dataset_id = ?)
                  )
                ORDER BY v.created_at DESC, v.id DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
        return dict(duplicate) if duplicate is not None else None

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
        if target is None or target["kind"] != "returns":
            raise ValueError("请选择有效的用户反馈数据源")
        if target["usage_scope"] != "managed":
            raise ValueError("一次性任务数据不能作为长期数据源更新")
        target_source_key = str(target["source_key"] or "")
        if target_source_key and source_key and target_source_key != source_key:
            raise ValueError("上传文件与所选数据源的店铺/站点不一致")

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
        dataset_name = ""
        dataset_description = ""
        usage_scope = "managed"
        try:
            raw_destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, raw_destination)
            import_record = {
                "id": import_id,
                "raw_file_path": str(raw_destination),
                "original_name": original_name,
                "content_type": content_type,
                "size_bytes": raw_destination.stat().st_size,
                "raw_sha256": inspection["raw_sha256"],
                "row_count": inspection["row_count"],
                "column_count": inspection["column_count"],
                "schema_json": json_text(inspection["schema"]),
                "quality_json": json_text(inspection["quality"]),
                "imported_row_count": imported_row_count,
                "skipped_row_count": skipped_row_count,
            }
            if mode in {"analyze_only", "create"}:
                effective_dataset_id = new_id("ds")
                dataset_name = name.strip() or str(inspection["suggested_name"])
                dataset_description = (
                    "仅用于一次分析的用户反馈数据"
                    if mode == "analyze_only"
                    else "持续维护的用户反馈数据源"
                )
                usage_scope = "task_input" if mode == "analyze_only" else "managed"
                prepared = self._prepare_return_version(
                    source_path=source_path,
                    original_name=original_name,
                    content_type=content_type,
                    change_note=generated_note or "首次导入用户反馈数据",
                    inspection=inspection,
                )
            elif mode == "replace":
                assert target is not None
                dataset_name = str(target["name"])
                dataset_description = str(target["description"])
                usage_scope = str(target["usage_scope"])
                prepared = self._prepare_return_version(
                    source_path=source_path,
                    original_name=original_name,
                    content_type=content_type,
                    change_note=generated_note or "替换当前用户反馈数据",
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
        result_dataset_id = str(outcome["dataset_id"])
        refreshed = self.get(result_dataset_id) or target or {}
        return {
            "dataset": refreshed,
            "version_id": str(outcome["version_id"]),
            "duplicate": bool(outcome["duplicate"]),
            "mode": mode,
            "inspection": inspection,
            "summary": {
                "imported_row_count": imported_row_count,
                "skipped_row_count": skipped_row_count,
            },
        }
