from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from web_backend.common import add_audit, json_text, json_value, new_id
from web_backend.database import Database
from web_backend.dataset_files import (
    ALLOWED_EXTENSIONS as ALLOWED_EXTENSIONS,
)
from web_backend.dataset_files import (
    PRODUCT_WORKSHEET as PRODUCT_WORKSHEET,
)
from web_backend.dataset_files import (
    DatasetRevisionConflict as DatasetRevisionConflict,
)
from web_backend.dataset_files import (
    _fill_missing_return_store,
    _inspect_file_with_frame,
    _return_source_key,
    _return_source_name,
    _sha256_file,
)
from web_backend.dataset_files import (
    inspect_file as inspect_file,
)
from web_backend.dataset_product_workbook import DatasetProductWorkbookMixin
from web_backend.dataset_return_import import DatasetReturnImportMixin
from web_backend.dataset_return_versions import (
    RETURN_APPEND_MAX_ATTEMPTS as RETURN_APPEND_MAX_ATTEMPTS,
)
from web_backend.dataset_return_versions import (
    DatasetReturnVersionMixin,
)
from web_backend.dataset_storage import DatasetStorageMixin
from web_backend.dataset_storage import shutil as shutil
from web_backend.datasets.catalog import _DatasetCatalog
from web_backend.datasets.preview import _DatasetPreview
from web_backend.datasets.references import _DatasetReferences
from web_backend.security import utc_now
from web_backend.settings import Settings


class DatasetService(
    _DatasetCatalog,
    _DatasetReferences,
    _DatasetPreview,
    DatasetStorageMixin,
    DatasetReturnVersionMixin,
    DatasetReturnImportMixin,
    DatasetProductWorkbookMixin,
):
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings

    def inspect_return_import(
        self,
        source_path: Path,
        original_name: str,
        actor_id: str | None = None,
        content_type: str = "text/csv",
    ) -> dict[str, Any]:
        row_count, column_count, schema, quality = inspect_file(
            source_path,
            "returns",
        )
        raw_sha256 = _sha256_file(source_path)
        stores = [str(value) for value in quality.get("stores", [])]
        source_key = _return_source_key(stores)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT d.id AS dataset_id, d.name AS dataset_name,
                       d.source_key, d.current_version,
                       v.id AS version_id, v.row_count, v.quality_json,
                       v.created_at AS version_created_at
                FROM datasets d
                JOIN dataset_versions v
                  ON v.dataset_id = d.id AND v.version = d.current_version
                WHERE d.kind = 'returns'
                  AND d.usage_scope = 'managed'
                  AND d.archived_at IS NULL
                ORDER BY d.updated_at DESC, d.id
                """
            ).fetchall()
            duplicate = self._find_duplicate_return_import(
                connection,
                raw_sha256=raw_sha256,
                mode="analyze_only",
                dataset_id="",
            )
        matches = []
        for row in rows:
            item = dict(row)
            item_quality = json_value(item.pop("quality_json", None), {})
            item_source_key = str(item.get("source_key") or "") or _return_source_key(
                item_quality.get("stores", [])
            )
            if source_key and item_source_key == source_key:
                item["source_key"] = item_source_key
                matches.append(item)
        inspection = {
            "original_name": original_name,
            "raw_sha256": raw_sha256,
            "row_count": row_count,
            "column_count": column_count,
            "schema": schema,
            "quality": quality,
            "stores": stores,
            "source_key": source_key,
            "suggested_name": _return_source_name(stores, original_name),
            "matches": matches,
            "duplicate": dict(duplicate) if duplicate is not None else None,
        }
        if actor_id is not None:
            self._cleanup_staged_imports()
            inspection_id = new_id("inspection")
            created_at = datetime.now(timezone.utc)
            expires_at = created_at + timedelta(minutes=30)
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    """
                    INSERT INTO dataset_import_staging(
                        id, owner_id, temp_path, original_name, content_type,
                        size_bytes, sha256, inspection_json, created_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        inspection_id,
                        actor_id,
                        str(source_path),
                        original_name,
                        content_type,
                        source_path.stat().st_size,
                        raw_sha256,
                        json_text(inspection),
                        created_at.isoformat(),
                        expires_at.isoformat(),
                    ),
                )
            inspection["inspection_id"] = inspection_id
        return inspection

    def create(
        self,
        name: str,
        kind: str,
        description: str,
        source_path: Path,
        original_name: str,
        content_type: str,
        change_note: str,
        actor_id: str,
        default_store: str = "",
        source_key: str = "",
        usage_scope: str = "managed",
        _inspection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        dataset_id = new_id("ds")
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO datasets(
                    id, name, kind, description, source_key, usage_scope,
                    current_version,
                    created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    dataset_id,
                    name.strip(),
                    kind,
                    description.strip(),
                    source_key.strip() or None,
                    usage_scope,
                    actor_id,
                    now,
                    now,
                ),
            )
        try:
            self.add_version(
                dataset_id=dataset_id,
                source_path=source_path,
                original_name=original_name,
                content_type=content_type,
                change_note=change_note or "创建首个版本",
                actor_id=actor_id,
                default_store=default_store,
                _inspection=_inspection,
            )
        except Exception:
            with self.database.transaction() as connection:
                connection.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
            raise
        add_audit(
            self.database,
            "dataset",
            dataset_id,
            "create",
            actor_id,
            after={"name": name, "kind": kind},
        )
        return self.get(dataset_id) or {}

    def add_version(
        self,
        dataset_id: str,
        source_path: Path,
        original_name: str,
        content_type: str,
        change_note: str,
        actor_id: str,
        expected_current_version: int | None = None,
        default_store: str = "",
        _inspection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            dataset = connection.execute(
                "SELECT * FROM datasets WHERE id = ? AND archived_at IS NULL",
                (dataset_id,),
            ).fetchone()
        if dataset is None:
            raise ValueError("数据集不存在")
        kind = str(dataset["kind"])
        if kind == "returns":
            _fill_missing_return_store(source_path, default_store)
        inspected_frame: pd.DataFrame | None = None
        # 仅复用同次导入在服务端产生的检查结果，修改文件后必须重新检查。
        if _inspection is not None and not default_store:
            row_count = _inspection["row_count"]
            column_count = _inspection["column_count"]
            schema = _inspection["schema"]
            quality = _inspection["quality"]
            digest = _inspection["raw_sha256"]
        else:
            (
                inspected_frame,
                row_count,
                column_count,
                schema,
                quality,
            ) = _inspect_file_with_frame(source_path, kind)
            digest = _sha256_file(source_path)
        destination = self._ensure_blob(source_path, digest)
        if kind == "products":
            self._ensure_product_preview(destination, digest, inspected_frame)
        prepared = self._prepared_version(
            destination=destination,
            original_name=original_name,
            content_type=content_type,
            change_note=change_note.strip(),
            digest=digest,
            row_count=row_count,
            column_count=column_count,
            schema=schema,
            quality=quality,
        )
        version_id = str(prepared["id"])

        with self.database.transaction(immediate=True) as connection:
            now = utc_now()
            version = self._insert_prepared_version(
                connection,
                dataset_id=dataset_id,
                prepared=prepared,
                actor_id=actor_id,
                now=now,
                expected_current_version=expected_current_version,
            )
        add_audit(
            self.database,
            "dataset",
            dataset_id,
            "add_version",
            actor_id,
            after={
                "version": version,
                "version_id": version_id,
                "default_store": default_store.strip(),
            },
        )
        return self.get(dataset_id) or {}
