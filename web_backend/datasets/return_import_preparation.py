import shutil
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from web_backend.common import json_text, new_id


def validate_return_target(target: Mapping[str, Any] | None, source_key: str) -> None:
    if target is None or target["kind"] != "returns":
        raise ValueError("请选择有效的用户反馈数据源")
    if target.get("usage_scope") != "managed":
        raise ValueError("一次性任务数据不能作为长期数据源更新")
    target_source_key = str(target.get("source_key") or "")
    if target_source_key and source_key and target_source_key != source_key:
        raise ValueError("上传文件与所选数据源的店铺/站点不一致")


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
    _prepare_return_version: Callable[..., dict[str, Any]]

    def _prepare_non_appended_return_import(
        self,
        mode: str,
        target: dict[str, Any] | None,
        source_path: Path,
        inspection: dict[str, Any],
        options: dict[str, str],
    ) -> tuple[str, str, str, str, dict[str, Any]]:
        if mode in {"analyze_only", "create"}:
            effective_dataset_id = new_id("ds")
            dataset_name = options["name"].strip() or str(inspection["suggested_name"])
            dataset_description = (
                "仅用于一次分析的用户反馈数据"
                if mode == "analyze_only"
                else "持续维护的用户反馈数据源"
            )
            usage_scope = "task_input" if mode == "analyze_only" else "managed"
            prepared = self._prepare_return_version(
                source_path=source_path,
                original_name=options["original_name"],
                content_type=options["content_type"],
                change_note=options["generated_note"] or "首次导入用户反馈数据",
                inspection=inspection,
            )
        else:
            assert target is not None
            effective_dataset_id = options["dataset_id"]
            dataset_name = str(target["name"])
            dataset_description = str(target["description"])
            usage_scope = str(target["usage_scope"])
            prepared = self._prepare_return_version(
                source_path=source_path,
                original_name=options["original_name"],
                content_type=options["content_type"],
                change_note=options["generated_note"] or "替换当前用户反馈数据",
            )
        return (
            effective_dataset_id,
            dataset_name,
            dataset_description,
            usage_scope,
            prepared,
        )

    def _return_import_result(
        self,
        outcome: dict[str, Any],
        target: dict[str, Any] | None,
        inspection: dict[str, Any],
        mode: str,
        summary: dict[str, int],
    ) -> dict[str, Any]:
        result_dataset_id = str(outcome["dataset_id"])
        refreshed = self.get(result_dataset_id) or target or {}
        return {
            "dataset": refreshed,
            "version_id": str(outcome["version_id"]),
            "duplicate": bool(outcome["duplicate"]),
            "mode": mode,
            "inspection": inspection,
            "summary": summary,
        }

    def _duplicate_return_import(
        self,
        *,
        mode: str,
        dataset_id: str,
        inspection: dict[str, Any],
    ) -> dict[str, Any] | None:
        duplicate = inspection.get("duplicate")
        if not isinstance(duplicate, dict):
            return None
        duplicate_in_target = (
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
