from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from return_semantics.data import read_return_csv
from web_backend.common import insert_audit, json_text, new_id
from web_backend.database import Database
from web_backend.dataset_files import (
    DatasetRevisionConflict,
    _inspect_file_with_frame,
    _sha256_file,
)
from web_backend.security import utc_now
from web_backend.settings import Settings

RETURN_APPEND_MAX_ATTEMPTS = 3


class DatasetReturnVersionMixin:
    database: Database
    settings: Settings
    get: Callable[..., dict[str, Any] | None]
    _ensure_blob: Callable[..., Path]
    _find_duplicate_return_import: Callable[..., dict[str, Any] | None]
    _validate_return_import_target: Callable[..., None]

    def _prepare_return_version(
        self,
        *,
        source_path: Path,
        original_name: str,
        content_type: str,
        change_note: str,
        inspection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if inspection is None:
            _, row_count, column_count, schema, quality = _inspect_file_with_frame(
                source_path,
                "returns",
            )
            digest = _sha256_file(source_path)
        else:
            row_count = int(inspection["row_count"])
            column_count = int(inspection["column_count"])
            schema = inspection["schema"]
            quality = inspection["quality"]
            digest = str(inspection["raw_sha256"])
        destination = self._ensure_blob(source_path, digest)
        return self._prepared_version(
            destination=destination,
            original_name=original_name,
            content_type=content_type,
            change_note=change_note,
            digest=digest,
            row_count=row_count,
            column_count=column_count,
            schema=schema,
            quality=quality,
        )

    @staticmethod
    def _prepared_version(
        *,
        destination: Path,
        original_name: str,
        content_type: str,
        change_note: str,
        digest: str,
        row_count: int,
        column_count: int,
        schema: list[dict[str, str]],
        quality: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "id": new_id("dsv"),
            "file_path": str(destination),
            "original_name": original_name,
            "content_type": content_type,
            "size_bytes": destination.stat().st_size,
            "sha256": digest,
            "row_count": row_count,
            "column_count": column_count,
            "schema_json": json_text(schema),
            "quality_json": json_text(quality),
            "change_note": change_note,
        }

    def _prepare_appended_return_version(
        self,
        *,
        target: dict[str, Any],
        incoming_frame: pd.DataFrame,
        original_name: str,
        change_note: str,
    ) -> tuple[dict[str, Any], int, int, int]:
        expected_version = int(target["current_version"])
        current_version = next(
            value
            for value in target["versions"]
            if value["version"] == expected_version
        )
        with self.database.connect() as connection:
            current_row = connection.execute(
                "SELECT file_path FROM dataset_versions WHERE id = ?",
                (current_version["id"],),
            ).fetchone()
        current_frame = read_return_csv(Path(str(current_row["file_path"])))
        columns = list(dict.fromkeys([*current_frame.columns, *incoming_frame.columns]))
        current_frame = current_frame.reindex(columns=columns)
        current_incoming = incoming_frame.reindex(columns=columns)
        clean_current = current_frame.drop_duplicates(ignore_index=True)
        merged = pd.concat(
            [clean_current, current_incoming],
            ignore_index=True,
        ).drop_duplicates(ignore_index=True)
        imported_row_count = max(len(merged) - len(clean_current), 0)
        skipped_row_count = max(len(current_incoming) - imported_row_count, 0)
        merge_path = self.settings.data_dir / "tmp" / f"{new_id('merge')}.csv"
        merge_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            merged.to_csv(merge_path, index=False, encoding="utf-8-sig")
            prepared = self._prepare_return_version(
                source_path=merge_path,
                original_name=original_name,
                content_type="text/csv",
                change_note=change_note or "追加一批退货数据",
            )
        finally:
            merge_path.unlink(missing_ok=True)
        return (
            prepared,
            imported_row_count,
            skipped_row_count,
            expected_version,
        )

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
        mode: str,
        dataset_id: str,
        dataset_name: str,
        dataset_description: str,
        usage_scope: str,
        source_key: str,
        prepared: dict[str, Any],
        import_record: dict[str, Any],
        actor_id: str,
        expected_current_version: int | None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            duplicate = self._find_duplicate_return_import(
                connection,
                raw_sha256=str(import_record["raw_sha256"]),
                mode=mode,
                dataset_id=dataset_id,
            )
            if duplicate is not None:
                return {
                    "dataset_id": str(duplicate["dataset_id"]),
                    "version_id": str(duplicate["version_id"]),
                    "duplicate": True,
                }
            self._validate_return_import_target(
                connection,
                mode=mode,
                dataset_id=dataset_id,
                source_key=source_key,
            )
            if mode in {"analyze_only", "create"}:
                connection.execute(
                    """
                    INSERT INTO datasets(
                        id, name, kind, description, source_key, usage_scope,
                        current_version, created_by, created_at, updated_at
                    ) VALUES (?, ?, 'returns', ?, ?, ?, 0, ?, ?, ?)
                    """,
                    (
                        dataset_id,
                        dataset_name,
                        dataset_description,
                        source_key or None,
                        usage_scope,
                        actor_id,
                        now,
                        now,
                    ),
                )
            version = self._insert_prepared_version(
                connection,
                dataset_id=dataset_id,
                prepared=prepared,
                actor_id=actor_id,
                now=now,
                expected_current_version=expected_current_version,
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
            if mode in {"analyze_only", "create"}:
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
                    mode,
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
                    "mode": mode,
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

    def _commit_appended_return_import(
        self,
        *,
        dataset_id: str,
        target: dict[str, Any],
        source_path: Path,
        original_name: str,
        change_note: str,
        source_key: str,
        import_record: dict[str, Any],
        actor_id: str,
    ) -> tuple[dict[str, Any], int, int, dict[str, Any]]:
        incoming_frame = read_return_csv(source_path)
        current_target = target
        for attempt in range(RETURN_APPEND_MAX_ATTEMPTS):
            (
                prepared,
                imported_row_count,
                skipped_row_count,
                expected_version,
            ) = self._prepare_appended_return_version(
                target=current_target,
                incoming_frame=incoming_frame,
                original_name=original_name,
                change_note=change_note,
            )
            import_record["imported_row_count"] = imported_row_count
            import_record["skipped_row_count"] = skipped_row_count
            try:
                outcome = self._commit_return_import(
                    mode="append",
                    dataset_id=dataset_id,
                    dataset_name=str(target["name"]),
                    dataset_description=str(target["description"]),
                    usage_scope=str(target["usage_scope"]),
                    source_key=source_key,
                    prepared=prepared,
                    import_record=import_record,
                    actor_id=actor_id,
                    expected_current_version=expected_version,
                )
                return (
                    prepared,
                    imported_row_count,
                    skipped_row_count,
                    outcome,
                )
            except DatasetRevisionConflict as exc:
                if attempt + 1 >= RETURN_APPEND_MAX_ATTEMPTS:
                    raise DatasetRevisionConflict(
                        "退货数据已被其他用户连续修改，请刷新后重试"
                    ) from exc
                refreshed = self.get(dataset_id, include={"versions"})
                if refreshed is None:
                    raise ValueError("退货数据源不存在") from exc
                current_target = refreshed

        raise DatasetRevisionConflict("退货数据已被其他用户连续修改，请刷新后重试")

    @staticmethod
    def _cleanup_import_source(raw_destination: Path) -> None:
        raw_destination.unlink(missing_ok=True)
        try:
            raw_destination.parent.rmdir()
        except OSError:
            pass
