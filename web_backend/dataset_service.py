from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from return_semantics.data import PRODUCT_COLUMNS, read_return_file
from web_backend.common import add_audit, json_text, json_value, list_audit, new_id
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
from web_backend.security import utc_now
from web_backend.settings import Settings


class DatasetService(
    DatasetStorageMixin,
    DatasetReturnVersionMixin,
    DatasetReturnImportMixin,
    DatasetProductWorkbookMixin,
):
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings

    def list(
        self,
        kind: str | None = None,
        usage_scope: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT d.*, u.display_name AS creator_name,
                   (SELECT COUNT(DISTINCT task.id)
                    FROM dataset_versions referenced_version
                    JOIN tasks task
                      ON task.dataset_version_id = referenced_version.id
                      OR task.product_version_id = referenced_version.id
                    WHERE referenced_version.dataset_id = d.id
                   ) AS task_reference_count,
                   v.id AS version_id, v.original_name, v.row_count,
                   v.column_count, v.size_bytes, v.schema_json,
                   v.quality_json, v.created_at AS version_created_at
            FROM datasets d
            JOIN users u ON u.id = d.created_by
            LEFT JOIN dataset_versions v
              ON v.dataset_id = d.id AND v.version = d.current_version
            WHERE d.archived_at IS NULL
        """
        params: list[object] = []
        if kind:
            query += " AND d.kind = ?"
            params.append(kind)
        if usage_scope:
            query += " AND d.usage_scope = ?"
            params.append(usage_scope)
        query += " ORDER BY d.updated_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._serialize(dict(row)) for row in rows]

    def get(
        self,
        dataset_id: str,
        include: set[str] | None = None,
    ) -> dict[str, Any] | None:
        requested = {"versions", "imports", "audit"} if include is None else include
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT d.*, u.display_name AS creator_name,
                       (SELECT COUNT(DISTINCT task.id)
                        FROM dataset_versions referenced_version
                        JOIN tasks task
                          ON task.dataset_version_id = referenced_version.id
                          OR task.product_version_id = referenced_version.id
                        WHERE referenced_version.dataset_id = d.id
                       ) AS task_reference_count,
                       v.id AS version_id, v.original_name, v.row_count,
                       v.column_count, v.size_bytes, v.schema_json,
                       v.quality_json, v.created_at AS version_created_at
                FROM datasets d
                JOIN users u ON u.id = d.created_by
                LEFT JOIN dataset_versions v
                  ON v.dataset_id = d.id AND v.version = d.current_version
                WHERE d.id = ? AND d.archived_at IS NULL
                """,
                (dataset_id,),
            ).fetchone()
            if row is None:
                return None
            versions = (
                connection.execute(
                    """
                    SELECT v.*, u.display_name AS creator_name
                    FROM dataset_versions v
                    JOIN users u ON u.id = v.created_by
                    WHERE v.dataset_id = ?
                    ORDER BY v.version DESC
                    """,
                    (dataset_id,),
                ).fetchall()
                if "versions" in requested
                else []
            )
            imports = (
                connection.execute(
                    """
                    SELECT i.*, u.display_name AS creator_name
                    FROM dataset_imports i
                    JOIN users u ON u.id = i.created_by
                    WHERE i.dataset_id = ?
                    ORDER BY i.created_at DESC, i.id DESC
                    """,
                    (dataset_id,),
                ).fetchall()
                if "imports" in requested
                else []
            )
        item = self._serialize(dict(row))
        if "versions" in requested:
            item["versions"] = [
                self._serialize_version(dict(value)) for value in versions
            ]
        if "imports" in requested:
            item["imports"] = [self._serialize_import(dict(value)) for value in imports]
        if "audit" in requested:
            item["audit"] = list_audit(self.database, "dataset", dataset_id)
        return item

    def list_versions(self, kind: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT v.*, d.name AS dataset_name, d.kind, d.current_version,
                   d.source_key, d.usage_scope,
                   u.display_name AS creator_name
            FROM dataset_versions v
            JOIN datasets d ON d.id = v.dataset_id
            JOIN users u ON u.id = v.created_by
            WHERE d.archived_at IS NULL
        """
        params: tuple[object, ...] = ()
        if kind:
            query += " AND d.kind = ?"
            params = (kind,)
        query += " ORDER BY v.created_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        output = []
        for row in rows:
            item = self._serialize_version(dict(row))
            item["version_id"] = item["id"]
            output.append(item)
        return output

    def references(
        self,
        version_id: str,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            version = connection.execute(
                """
                SELECT v.id, v.dataset_id, v.version, v.sha256,
                       d.name AS dataset_name, d.kind
                FROM dataset_versions v
                JOIN datasets d ON d.id = v.dataset_id
                WHERE v.id = ?
                """,
                (version_id,),
            ).fetchone()
            if version is None:
                raise ValueError("数据版本不存在")
            total = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM tasks t
                    WHERE t.dataset_version_id = ? OR t.product_version_id = ?
                    """,
                    (version_id, version_id),
                ).fetchone()[0]
            )
            rows = connection.execute(
                """
                SELECT t.id AS task_id, t.title, t.status,
                       t.owner_id, owner.display_name AS owner_name,
                       t.created_at, t.snapshot_json,
                       CASE WHEN t.dataset_version_id = ?
                            THEN 'returns' ELSE 'products' END AS reference_type
                FROM tasks t
                LEFT JOIN users owner ON owner.id = t.owner_id
                WHERE t.dataset_version_id = ? OR t.product_version_id = ?
                ORDER BY t.created_at DESC, t.id ASC, reference_type ASC
                LIMIT ? OFFSET ?
                """,
                (
                    version_id,
                    version_id,
                    version_id,
                    page_size,
                    (page - 1) * page_size,
                ),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            snapshot = json_value(item.pop("snapshot_json"), {}) or {}
            item["owner"] = {
                "id": item.pop("owner_id"),
                "name": item.pop("owner_name"),
            }
            item["version_snapshot"] = snapshot.get(item["reference_type"], {})
            items.append(item)
        return {
            "version": {
                "id": version["id"],
                "dataset_id": version["dataset_id"],
                "name": version["dataset_name"],
                "kind": version["kind"],
                "version": int(version["version"]),
                "sha256": version["sha256"],
            },
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def version_file(
        self,
        dataset_id: str,
        version: int | None = None,
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT v.file_path, v.original_name, v.content_type, v.version
                FROM dataset_versions v
                JOIN datasets d ON d.id = v.dataset_id
                WHERE v.dataset_id = ? AND d.archived_at IS NULL
                  AND v.version = COALESCE(?, d.current_version)
                """,
                (dataset_id, version),
            ).fetchone()
        return dict(row) if row else None

    def product_scopes(self, version_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT v.file_path, d.kind
                FROM dataset_versions v
                JOIN datasets d ON d.id = v.dataset_id
                WHERE v.id = ? AND d.archived_at IS NULL
                """,
                (version_id,),
            ).fetchone()
        if row is None or row["kind"] != "products":
            raise ValueError("商品维度版本不存在")
        frame = pd.read_excel(
            Path(str(row["file_path"])),
            sheet_name=PRODUCT_WORKSHEET,
            dtype=str,
            usecols=PRODUCT_COLUMNS,
        ).fillna("")
        frame["店铺/站点"] = frame["店铺/站点"].str.strip()
        frame["Listing"] = frame["Listing"].str.strip()
        output = []
        for store, rows in frame.loc[frame["店铺/站点"].ne("")].groupby(
            "店铺/站点",
            sort=True,
        ):
            output.append(
                {
                    "store": str(store),
                    "listings": sorted(
                        value for value in rows["Listing"].unique().tolist() if value
                    ),
                }
            )
        return output

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

    def preview_rows(
        self,
        dataset_id: str,
        offset: int = 0,
        limit: int = 50,
        query: str = "",
        store: str = "",
        category: str = "",
        version: int | None = None,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT d.kind, d.current_version, v.version AS selected_version,
                       v.file_path, v.sha256, v.row_count, v.quality_json
                FROM datasets d
                JOIN dataset_versions v
                  ON v.dataset_id = d.id
                 AND v.version = COALESCE(?, d.current_version)
                WHERE d.id = ? AND d.archived_at IS NULL
                """,
                (version, dataset_id),
            ).fetchone()
        if row is None:
            raise ValueError("数据集或数据版本不存在")
        if row["kind"] == "products":
            preview_path = self._ensure_product_preview(
                Path(str(row["file_path"])),
                str(row["sha256"]),
            )
            frame = pd.read_csv(preview_path, dtype=str).fillna("")
        else:
            if not query.strip() and not store.strip() and not category.strip():
                frame = read_return_file(
                    Path(str(row["file_path"])),
                    nrows=offset + limit,
                ).fillna("")
                selected = frame.iloc[offset : offset + limit].copy()
                records = selected.astype(str).to_dict(orient="records")
                for row_index, record in zip(selected.index, records, strict=True):
                    record["_row_index"] = int(row_index)
                quality = json_value(row["quality_json"], {}) or {}
                return {
                    "records": records,
                    "offset": offset,
                    "limit": limit,
                    "total": int(row["row_count"]),
                    "source_total": int(row["row_count"]),
                    "query": query,
                    "version": int(row["selected_version"]),
                    "facets": {
                        "stores": quality.get("stores", []),
                        "categories": [],
                    },
                }
            frame = read_return_file(Path(str(row["file_path"]))).fillna("")
        source_total = len(frame)
        stores = (
            sorted(
                value
                for value in frame["店铺/站点"]
                .astype(str)
                .str.strip()
                .unique()
                .tolist()
                if value
            )
            if "店铺/站点" in frame.columns
            else []
        )
        if {"品类A", "品类B"}.issubset(frame.columns):
            category_a = frame["品类A"].astype(str).str.strip()
            category_b = frame["品类B"].astype(str).str.strip()
            category_labels = category_a.where(
                category_b.eq(""),
                category_a + " > " + category_b,
            )
            category_labels = category_labels.where(category_a.ne(""), category_b)
            categories = sorted(
                value for value in category_labels.unique().tolist() if value
            )
        else:
            category_labels = pd.Series("", index=frame.index, dtype=str)
            categories = []
        clean_store = store.strip()
        if clean_store and "店铺/站点" in frame.columns:
            frame = frame.loc[
                frame["店铺/站点"].astype(str).str.strip().eq(clean_store)
            ]
            category_labels = category_labels.loc[frame.index]
        clean_category = category.strip()
        if clean_category:
            frame = frame.loc[category_labels.eq(clean_category)]
        clean_query = query.strip().lower()
        if clean_query:
            searchable = frame.astype(str).apply(
                lambda column: column.str.lower().str.contains(
                    clean_query,
                    regex=False,
                )
            )
            frame = frame.loc[searchable.any(axis=1)]
        selected = frame.iloc[offset : offset + limit].copy()
        records = selected.astype(str).to_dict(orient="records")
        for row_index, record in zip(selected.index, records, strict=True):
            record["_row_index"] = int(row_index)
        return {
            "records": records,
            "offset": offset,
            "limit": limit,
            "total": len(frame),
            "source_total": source_total,
            "query": query,
            "version": int(row["selected_version"]),
            "facets": {"stores": stores, "categories": categories},
        }

    @staticmethod
    def _serialize(item: dict[str, Any]) -> dict[str, Any]:
        item["schema"] = json_value(item.pop("schema_json", None), [])
        item["quality"] = json_value(item.pop("quality_json", None), {})
        if item.get("kind") == "returns":
            stores = item["quality"].get("stores", [])
            if not item.get("source_key"):
                item["source_key"] = _return_source_key(stores)
            item["source_name"] = (
                _return_source_name(stores, "")
                if stores
                else str(item.get("name") or "未命名用户反馈数据")
            )
        return item

    @staticmethod
    def _serialize_version(item: dict[str, Any]) -> dict[str, Any]:
        item.pop("file_path", None)
        item["schema"] = json_value(item.pop("schema_json", None), [])
        item["quality"] = json_value(item.pop("quality_json", None), {})
        if item.get("kind") == "returns":
            stores = item["quality"].get("stores", [])
            if not item.get("source_key"):
                item["source_key"] = _return_source_key(stores)
            item["source_name"] = (
                _return_source_name(stores, "")
                if stores
                else str(item.get("dataset_name") or "未命名用户反馈数据")
            )
        return item

    @staticmethod
    def _serialize_import(item: dict[str, Any]) -> dict[str, Any]:
        item.pop("raw_file_path", None)
        item["schema"] = json_value(item.pop("schema_json", None), [])
        item["quality"] = json_value(item.pop("quality_json", None), {})
        return item
