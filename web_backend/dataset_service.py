from __future__ import annotations

from pathlib import Path
from typing import Any

from web_backend.common import add_audit, new_id
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
    DatasetReturnVersionMixin,
    DatasetVersionWrite,
)
from web_backend.datasets.catalog import _DatasetCatalog
from web_backend.datasets.current_products import (
    refresh_product_dependents,
    update_current_products,
)
from web_backend.datasets.preview import _DatasetPreview
from web_backend.datasets.references import _DatasetReferences
from web_backend.datasets.return_inspection import (
    DatasetFilePreparationMixin,
    persist_return_inspection,
)
from web_backend.datasets.storage_files import StorageFilesMixin
from web_backend.security import utc_now
from web_backend.settings import Settings


class DatasetService(
    _DatasetCatalog,
    _DatasetReferences,
    _DatasetPreview,
    StorageFilesMixin,
    DatasetReturnVersionMixin,
    DatasetReturnImportMixin,
    DatasetProductWorkbookMixin,
    DatasetFilePreparationMixin,
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
            duplicate = self._find_duplicate_return_import(
                connection,
                raw_sha256=raw_sha256,
            )
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
            "duplicate": dict(duplicate) if duplicate is not None else None,
        }
        if actor_id is not None:
            self._cleanup_staged_imports()
            inspection["inspection_id"] = persist_return_inspection(
                self.database, source_path, actor_id, content_type, inspection
            )
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
        source_key: str = "",
        usage_scope: str = "",
        _inspection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        usage_scope = usage_scope or ("task_input" if kind == "returns" else "managed")
        if kind == "returns" and usage_scope != "task_input":
            raise ValueError("长期反馈数据源已下线，请通过分析任务导入数据")
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
                change_note=change_note
                or ("导入商品信息" if kind == "products" else "创建任务输入"),
                actor_id=actor_id,
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
        _inspection: dict[str, Any] | None = None,
        _product_previous_identities: list[tuple[str, str]] | None = None,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            dataset = connection.execute(
                "SELECT * FROM datasets WHERE id = ? AND archived_at IS NULL",
                (dataset_id,),
            ).fetchone()
        if dataset is None:
            raise ValueError("数据集不存在")
        kind = str(dataset["kind"])
        if kind == "products" and dataset["current_version"]:
            expected_current_version = (
                int(dataset["current_version"])
                if expected_current_version is None
                else expected_current_version
            )
            with self.database.connect() as connection:
                previous = connection.execute(
                    "SELECT file_path, sha256 FROM dataset_versions WHERE dataset_id = ? AND version = ?",
                    (dataset_id, dataset["current_version"]),
                ).fetchone()
            # 输入文件按摘要留存，正在执行的任务继续读取启动时的资料。
            self._ensure_blob(Path(previous["file_path"]), previous["sha256"])
        if kind == "returns" and (
            dataset["usage_scope"] != "task_input" or dataset["current_version"] != 0
        ):
            raise ValueError("任务输入快照不能更新，请在分析任务中重新导入")
        prepared = self._prepare_dataset_file(
            source_path,
            kind,
            _inspection,
            {
                "original_name": original_name,
                "content_type": content_type,
                "change_note": change_note,
            },
        )
        version_id = str(prepared["id"])
        prepared["manual_edit"] = _product_previous_identities is not None

        with self.database.transaction(immediate=True) as connection:
            now = utc_now()
            write = DatasetVersionWrite(
                dataset_id=dataset_id,
                prepared=prepared,
                actor_id=actor_id,
                expected_current_version=expected_current_version,
            )
            if kind == "products" and dataset["current_version"]:
                version, version_id = update_current_products(connection, write, now)
                refresh_product_dependents(
                    self.database,
                    connection,
                    dataset_id,
                    now,
                    previous_identities=_product_previous_identities,
                )
            else:
                version = self._insert_prepared_version(
                    connection, write=write, now=now
                )
        if not dataset["current_version"]:
            add_audit(
                self.database,
                "dataset",
                dataset_id,
                "import",
                actor_id,
                after={"version": version, "version_id": version_id},
            )
        return self.get(dataset_id) or {}
